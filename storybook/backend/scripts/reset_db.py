#!/usr/bin/env python3
"""
Reset Database Script
Clears all collections in the MongoDB database for local development.
WARNING: This will delete ALL data in the database!
"""
import sys
from reset_utils import reset_database

if __name__ == "__main__":
    # Confirm action
    print("=" * 60)
    print("WARNING: This will delete ALL data in the database!")
    print("=" * 60)
    response = input("\nAre you sure you want to continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        try:
            reset_database()
            print("\n✅ Database reset complete!")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)
    else:
        print("\n❌ Database reset cancelled.")
        sys.exit(0)
