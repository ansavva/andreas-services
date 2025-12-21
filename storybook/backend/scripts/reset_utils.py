"""
Shared utilities for reset scripts
"""
import os
import sys
import shutil
import time
import requests
from pymongo import MongoClient
from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env file"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)


def reset_database():
    """Reset all collections in the database"""
    load_env()

    # Get database URL from environment
    database_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/storybook_dev')

    # Extract database name from URL
    database_name = database_url.split('/')[-1]

    print(f"\n📊 Database: {database_url}")

    # Connect to MongoDB
    client = MongoClient(database_url)
    db = client[database_name]

    # List of collections to clear
    collections = [
        'story_projects',
        'child_profiles',
        'images',
        'character_assets',
        'story_states',
        'story_pages',
        'chat_messages',
        'projects'
    ]

    print("\nClearing database collections...\n")

    total_deleted = 0
    for collection_name in collections:
        if collection_name in db.list_collection_names():
            count = db[collection_name].count_documents({})
            result = db[collection_name].delete_many({})
            total_deleted += result.deleted_count
            print(f"  ✓ {collection_name}: {result.deleted_count} documents")
        else:
            print(f"  - {collection_name}: does not exist")

    # Close connection
    client.close()

    print(f"\n✅ Database cleared: {total_deleted} documents deleted")


def reset_storage():
    """Reset the storage directory"""
    load_env()

    # Get storage path from environment
    storage_path = os.getenv('FILE_STORAGE_PATH', './storage')

    # Convert to absolute path
    if not os.path.isabs(storage_path):
        storage_path = os.path.join(os.path.dirname(__file__), '..', storage_path)
        storage_path = os.path.abspath(storage_path)

    print(f"\n📁 Storage: {storage_path}")

    if not os.path.exists(storage_path):
        print("\n  ✓ Storage directory does not exist. Creating it...")
        os.makedirs(storage_path, exist_ok=True)
        print(f"✅ Storage directory created")
        return

    print("\nClearing storage directory...\n")

    # Count files before deletion
    file_count = 0
    for root, dirs, files in os.walk(storage_path):
        file_count += len(files)

    # Remove all contents
    deleted_count = 0
    for item in os.listdir(storage_path):
        item_path = os.path.join(storage_path, item)
        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
                deleted_count += 1
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                deleted_count += 1
        except Exception as e:
            print(f"  ✗ Failed to delete {item}: {e}")

    print(f"  ✓ Deleted {deleted_count} item(s)")
    print(f"\n✅ Storage cleared: {file_count} file(s) deleted")


def reset_replicate():
    """Delete all Replicate models based on database model_projects"""
    load_env()

    API_BASE = "https://api.replicate.com/v1"

    # Get Replicate API token
    api_token = os.getenv('REPLICATE_API_TOKEN')
    if not api_token:
        print("\n⚠️  Warning: REPLICATE_API_TOKEN not found in .env file")
        print("   Skipping Replicate cleanup")
        return

    # Get database URL
    database_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/storybook_dev')
    database_name = database_url.split('/')[-1]

    # Create session with auth
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    })

    try:
        # Get account username
        resp = session.get(f"{API_BASE}/account", timeout=30)
        if resp.status_code != 200:
            print(f"\n⚠️  Warning: Failed to get Replicate account info: {resp.status_code}")
            print("   Skipping Replicate cleanup")
            return

        replicate_username = resp.json().get("username")
        print(f"\n🤖 Replicate: {replicate_username}")

        # Connect to MongoDB and get model projects
        client = MongoClient(database_url)
        db = client[database_name]
        projects = list(db.model_projects.find({}))
        client.close()

        # Pull stored Replicate model identifiers
        models = []
        for project in projects:
            model_identifier = project.get('replicate_model_id')
            if model_identifier:
                models.append(model_identifier)

        if not models:
            print("   No model identifiers found in database")
            print("\n✅ Replicate: No models to delete")
            return

        print(f"\nDeleting {len(models)} Replicate model(s)...\n")

        deleted_count = 0
        failed_count = 0

        for model_identifier in models:
            if "/" in model_identifier:
                owner, model_name = model_identifier.split("/", 1)
            else:
                owner, model_name = replicate_username, model_identifier
            model_id = f"{owner}/{model_name}"

            # List and delete all versions first
            version_url = f"{API_BASE}/models/{owner}/{model_name}/versions"
            version_ids = []

            while version_url:
                resp = session.get(version_url, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    for v in data.get("results", []):
                        vid = v.get("id")
                        if vid:
                            version_ids.append(vid)
                    version_url = data.get("next")
                else:
                    break

            # Delete versions
            for vid in reversed(version_ids):
                session.delete(f"{API_BASE}/models/{owner}/{model_name}/versions/{vid}", timeout=30)
                time.sleep(0.1)

            # Delete the model
            resp = session.delete(f"{API_BASE}/models/{owner}/{model_name}", timeout=30)
            if resp.status_code in (200, 202, 204):
                deleted_count += 1
                print(f"  ✓ {model_id}")
            else:
                failed_count += 1
                print(f"  ✗ {model_id}")

        print(f"\n✅ Replicate cleared: {deleted_count} model(s) deleted")
        if failed_count > 0:
            print(f"   ⚠️  Failed to delete: {failed_count} model(s)")

    except Exception as e:
        print(f"\n❌ Error during Replicate cleanup: {e}")
        print("   Continuing with other cleanup tasks...")
