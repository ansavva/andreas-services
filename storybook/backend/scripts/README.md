# Backend Utility Scripts

Collection of utility scripts for managing the Storybook backend during development.

## Reset Scripts

These scripts help you reset your local development environment.

### Prerequisites

Make sure your virtual environment is activated:
```bash
cd /Users/andreassavva/Repos/andreas-services/storybook/backend
source venv/bin/activate
```

### Available Scripts

#### 1. Reset Database Only
Clears all MongoDB collections while keeping storage files intact.

```bash
python scripts/reset_db.py
```

Collections cleared:
- `story_projects`
- `child_profiles`
- `images`
- `character_assets`
- `story_states`
- `story_pages`
- `chat_messages`
- `projects`

#### 2. Reset Storage Only
Deletes all files in the storage directory while keeping database intact.

```bash
python scripts/reset_storage.py
```

Clears: `./storage/` directory

#### 3. Reset Everything
Resets both database and storage in one command.

```bash
python scripts/reset_all.py
```

This is equivalent to running both `reset_db.py` and `reset_storage.py`.

### Safety Features

All scripts:
- ⚠️ Prompt for confirmation before deleting anything
- Show what will be deleted
- Display summary of actions taken
- Can be cancelled by typing "no" at the prompt

### Example Usage

```bash
$ python scripts/reset_all.py

============================================================
WARNING: This will delete ALL data!
  - All database collections will be cleared
  - All files in storage directory will be deleted
============================================================

Are you sure you want to continue? (yes/no): yes

============================================================
RESETTING DATABASE AND STORAGE
============================================================

📊 Database: mongodb://localhost:27017/storybook_dev

Clearing database collections...

  ✓ story_projects: 5 documents
  ✓ child_profiles: 3 documents
  ✓ images: 45 documents
  ✓ character_assets: 8 documents
  - story_states: does not exist
  - story_pages: does not exist
  - chat_messages: does not exist
  - projects: does not exist

✅ Database cleared: 61 documents deleted

📁 Storage: /Users/andreassavva/Repos/andreas-services/storybook/backend/storage

Clearing storage directory...

  ✓ Deleted 3 item(s)

✅ Storage cleared: 45 file(s) deleted

============================================================
✅ RESET COMPLETE!
============================================================

All data has been cleared. You can start fresh.
```

### Troubleshooting

**MongoDB Connection Error**
- Make sure MongoDB is running: `brew services start mongodb-community`
- Check your `.env` file has the correct `MONGODB_URL`

**Storage Path Not Found**
- The script will automatically create the storage directory if it doesn't exist
- Check your `.env` file has `FILE_STORAGE_PATH=./storage`

**Permission Denied**
- Make sure scripts are executable: `chmod +x scripts/*.py`
- Or run with python explicitly: `python scripts/reset_all.py`
