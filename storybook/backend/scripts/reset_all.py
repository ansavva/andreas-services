#!/usr/bin/env python3
"""
Reset All Script
Resets both the database and storage directory for local development.
WARNING: This will delete ALL data!
"""
import sys
from reset_utils import reset_database, reset_storage

if __name__ == "__main__":
    # Confirm action
    print("=" * 60)
    print("WARNING: This will delete ALL data!")
    print("  - All database collections will be cleared")
    print("  - All files in storage directory will be deleted")
    print("=" * 60)
    response = input("\nAre you sure you want to continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        try:
            print("\n" + "=" * 60)
            print("RESETTING DATABASE AND STORAGE")
            print("=" * 60)

            reset_database()
            reset_storage()

            print("\n" + "=" * 60)
            print("✅ RESET COMPLETE!")
            print("=" * 60)
            print("\nAll data has been cleared. You can start fresh.\n")

        except Exception as e:
            print(f"\n❌ Error during reset: {e}")
            sys.exit(1)
    else:
        print("\n❌ Reset cancelled.")
        sys.exit(0)
