import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
from werkzeug.datastructures import FileStorage

from src.storage.base import FileStorageAdapter

class FilesystemStorage(FileStorageAdapter):
    """Local filesystem storage adapter for development"""

    def __init__(self, base_path: str = "./storage"):
        self.base_path = Path(base_path).resolve()
        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, key: str) -> Path:
        """Convert a key to a full filesystem path"""
        # Remove leading slash if present
        key = key.lstrip('/')
        return self.base_path / key

    def upload_file(self, file: FileStorage, key: str) -> None:
        """Upload a file to local filesystem"""
        file_path = self._get_full_path(key)

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Save the file
        file.save(str(file_path))

    def download_file(self, key: str) -> Optional[bytes]:
        """Download a file from local filesystem"""
        file_path = self._get_full_path(key)

        if not file_path.exists():
            return None

        with open(file_path, 'rb') as f:
            return f.read()

    def delete_file(self, key: str) -> None:
        """Delete a file from local filesystem"""
        file_path = self._get_full_path(key)

        if file_path.exists():
            if file_path.is_file():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)

    def list_files(self, directory: str, include_children: bool = True) -> List[Dict]:
        """List files in a directory"""
        dir_path = self._get_full_path(directory)

        if not dir_path.exists():
            return []

        files = []

        if include_children:
            # Recursively list all files
            for root, dirs, filenames in os.walk(dir_path):
                for filename in filenames:
                    file_path = Path(root) / filename
                    # Get relative path from base_path
                    relative_path = file_path.relative_to(self.base_path)

                    files.append({
                        'Key': str(relative_path),
                        'LastModified': datetime.fromtimestamp(file_path.stat().st_mtime)
                    })
        else:
            # Only list immediate children (directories)
            if dir_path.is_dir():
                for item in dir_path.iterdir():
                    if item.is_dir():
                        # For directories, add trailing slash like S3
                        relative_path = item.relative_to(self.base_path)
                        files.append({
                            'Key': str(relative_path) + '/',
                            'LastModified': datetime.fromtimestamp(item.stat().st_mtime)
                        })

        # Sort by LastModified descending (newest first)
        files.sort(key=lambda x: x['LastModified'], reverse=True)

        return files

    def create_directory(self, key: str) -> None:
        """Create a directory"""
        dir_path = self._get_full_path(key)
        dir_path.mkdir(parents=True, exist_ok=True)
