"""
Shared utilities for reset scripts
"""
import os
import shutil
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
