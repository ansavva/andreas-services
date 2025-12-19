#!/usr/bin/env python3
"""
Reset Storage Script
Clears all files in the local storage directory for local development.
WARNING: This will delete ALL files in the storage directory!
"""
import sys
from reset_utils import reset_storage

if __name__ == "__main__":
    # Confirm action
    print("=" * 60)
    print("WARNING: This will delete ALL files in the storage directory!")
    print("=" * 60)
    response = input("\nAre you sure you want to continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        try:
            reset_storage()
            print("\n✅ Storage reset complete!")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)
    else:
        print("\n❌ Storage reset cancelled.")
        sys.exit(0)
