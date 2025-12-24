#!/usr/bin/env python3
"""
Delete a specific Replicate model by ID
Deletes all versions first, then deletes the model itself.
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv


API_BASE = "https://api.replicate.com/v1"


def list_versions(owner: str, model_name: str, api_token: str):
    """List all versions of a model"""
    version_ids = []
    url = f"{API_BASE}/models/{owner}/{model_name}/versions"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }

    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            print(f"⚠️  Warning: Failed to list versions: {resp.status_code}")
            return []

        data = resp.json()
        results = data.get("results", [])

        for v in results:
            vid = v.get("id")
            if vid:
                version_ids.append(vid)

        url = data.get("next")

    return version_ids


def delete_version(owner: str, model_name: str, version_id: str, api_token: str):
    """Delete a specific version of a model"""
    url = f"{API_BASE}/models/{owner}/{model_name}/versions/{version_id}"

    headers = {
        "Authorization": f"Bearer {api_token}",
    }

    resp = requests.delete(url, headers=headers, timeout=30)
    return resp.status_code in (200, 202, 204)


def delete_model(owner: str, model_name: str, api_token: str = None):
    """
    Deletes a Replicate model and all its versions.

    Args:
        owner (str): Username or organization that owns the model (e.g., "ansavva").
        model_name (str): Model name.
        api_token (str, optional): Replicate API token. If None, reads from REPLICATE_API_TOKEN env var.

    Returns:
        (success: bool, message: str)
    """
    # Read token from environment if not provided
    if api_token is None:
        api_token = os.getenv("REPLICATE_API_TOKEN")
        if not api_token:
            raise ValueError("API token must be provided or set in REPLICATE_API_TOKEN environment variable")

    model_id = f"{owner}/{model_name}"

    # Step 1: List all versions
    print(f"📋 Listing versions for {model_id}...")
    version_ids = list_versions(owner, model_name, api_token)

    if version_ids:
        print(f"   Found {len(version_ids)} version(s)")

        # Step 2: Delete all versions
        print(f"🗑️  Deleting versions...")
        deleted_versions = 0
        failed_versions = 0

        for vid in reversed(version_ids):
            if delete_version(owner, model_name, vid, api_token):
                print(f"   ✓ Deleted version {vid}")
                deleted_versions += 1
            else:
                print(f"   ✗ Failed to delete version {vid}")
                failed_versions += 1
            time.sleep(0.1)  # Rate limiting

        if failed_versions > 0:
            return False, f"Failed to delete {failed_versions} version(s). Cannot delete model."
    else:
        print(f"   No versions found")

    # Step 3: Delete the model itself
    print(f"🗑️  Deleting model {model_id}...")
    url = f"{API_BASE}/models/{owner}/{model_name}"

    headers = {
        "Authorization": f"Bearer {api_token}",
    }

    response = requests.delete(url, headers=headers, timeout=30)

    if response.status_code in (200, 202, 204):
        return True, "Model deleted successfully"
    else:
        return False, f"Failed to delete model: {response.status_code} - {response.text}"


if __name__ == "__main__":
    import argparse

    # Load environment variables from .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    parser = argparse.ArgumentParser(description="Delete a Replicate model")
    parser.add_argument("model_id", help="Full model identifier (owner/model-name).")
    parser.add_argument(
        "--token",
        help="Replicate API token (optional; if not provided uses REPLICATE_API_TOKEN)",
    )

    args = parser.parse_args()

    # Split into owner and model name
    try:
        owner, name = args.model_id.split("/", 1)
    except ValueError:
        print("❌ Error: Model identifier must be in the form owner/model-name")
        sys.exit(1)

    try:
        print("=" * 70)
        print(f"DELETING MODEL: {args.model_id}")
        print("=" * 70)
        print()

        success, message = delete_model(owner, name, api_token=args.token)

        print()
        print("=" * 70)
        if success:
            print(f"✅ SUCCESS: {message}")
        else:
            print(f"❌ FAILED: {message}")
        print("=" * 70)

        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
