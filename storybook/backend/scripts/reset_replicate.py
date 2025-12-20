#!/usr/bin/env python3
"""
Reset Replicate Models Script
Deletes all trained models from Replicate for the current user.
Uses MongoDB to find model projects and construct model names.
WARNING: This will delete ALL Replicate models!
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv
from pymongo import MongoClient


API_BASE = "https://api.replicate.com/v1"


def load_env():
    """Load environment variables from .env file"""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)


def get_account_username(session):
    """Get the account username from the Replicate API"""
    resp = session.get(f"{API_BASE}/account", timeout=30)
    if resp.status_code != 200:
        print(f"❌ Error: Failed to get account info: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json().get("username")


def get_models_from_database():
    """Get model projects from MongoDB and build model names"""
    load_env()

    # Get database URL from environment
    database_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/storybook_dev')
    database_name = database_url.split('/')[-1]

    # Connect to MongoDB
    client = MongoClient(database_url)
    db = client[database_name]

    # Get all model projects
    projects = list(db.model_projects.find({}))
    client.close()

    # Build model names: flux_{user_id}_{project_id}
    models = []
    for project in projects:
        project_id = str(project.get('_id'))
        user_id = project.get('user_id')
        if project_id and user_id:
            model_name = f"flux_{user_id}_{project_id}"
            models.append({
                'name': model_name,
                'project_id': project_id,
                'user_id': user_id
            })

    return models


def list_versions(session, owner, model_name):
    """List all versions of a model"""
    version_ids = []
    url = f"{API_BASE}/models/{owner}/{model_name}/versions"

    while url:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = data.get("results", [])

        for v in results:
            vid = v.get("id")
            if vid:
                version_ids.append(vid)

        url = data.get("next")

    return version_ids


def delete_version(session, owner, model_name, version_id):
    """Delete a specific version of a model"""
    url = f"{API_BASE}/models/{owner}/{model_name}/versions/{version_id}"
    resp = session.delete(url, timeout=30)
    return resp.status_code in (200, 202, 204)


def delete_model(session, owner, model_name):
    """Delete a model (only works when all versions are deleted)"""
    url = f"{API_BASE}/models/{owner}/{model_name}"
    resp = session.delete(url, timeout=30)
    return resp.status_code in (200, 202, 204)


def reset_replicate_models():
    """Delete all Replicate models for the current user"""
    load_env()

    # Get Replicate API token
    api_token = os.getenv('REPLICATE_API_TOKEN')
    if not api_token:
        print("❌ Error: REPLICATE_API_TOKEN not found in .env file")
        sys.exit(1)

    # Create session with auth
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    })

    try:
        print("\n🤖 Fetching account info...")
        replicate_username = get_account_username(session)

        print(f"🤖 Replicate Username: {replicate_username}")
        print("\n📊 Fetching model projects from database...\n")

        # Get models from database
        models = get_models_from_database()

        if not models:
            print("✓ No model projects found in database. Nothing to delete.")
            return

        print(f"Found {len(models)} model project(s) in database:\n")
        for i, model in enumerate(models, 1):
            model_name = model.get("name")
            print(f"  {i}. {replicate_username}/{model_name}")

        print("\n🗑️  Deleting models from Replicate...\n")

        deleted_count = 0
        failed_count = 0

        for model in models:
            model_name = model.get("name")
            model_id = f"{replicate_username}/{model_name}"

            print(f"  Deleting {model_id}...")

            # Delete all versions first
            version_ids = list_versions(session, replicate_username, model_name)
            if version_ids:
                print(f"    Found {len(version_ids)} version(s)")
                for vid in reversed(version_ids):
                    if delete_version(session, replicate_username, model_name, vid):
                        print(f"    ✓ Deleted version {vid}")
                    else:
                        print(f"    ✗ Failed to delete version {vid}")
                    time.sleep(0.1)

            # Delete the model
            if delete_model(session, replicate_username, model_name):
                print(f"  ✓ Deleted model")
                deleted_count += 1
            else:
                print(f"  ✗ Failed to delete model")
                failed_count += 1

        print(f"\n✅ Replicate cleanup complete:")
        print(f"   - Deleted: {deleted_count}")
        if failed_count > 0:
            print(f"   - Failed: {failed_count}")

    except Exception as e:
        print(f"\n❌ Error fetching models: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Confirm action
    print("=" * 60)
    print("WARNING: This will delete ALL Replicate models!")
    print("=" * 60)
    response = input("\nAre you sure you want to continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        try:
            print("\n" + "=" * 60)
            print("RESETTING REPLICATE MODELS")
            print("=" * 60)

            reset_replicate_models()

            print("\n" + "=" * 60)
            print("✅ RESET COMPLETE!")
            print("=" * 60)

        except Exception as e:
            print(f"\n❌ Error during reset: {e}")
            sys.exit(1)
    else:
        print("\n❌ Reset cancelled.")
        sys.exit(0)
