from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from werkzeug.datastructures import FileStorage

class FileStorageAdapter(ABC):
    """Abstract base class for file storage adapters"""

    @abstractmethod
    def upload_file(self, file: FileStorage, key: str) -> None:
        """Upload a file to storage"""
        pass

    @abstractmethod
    def download_file(self, key: str) -> Optional[bytes]:
        """Download a file from storage"""
        pass

    @abstractmethod
    def delete_file(self, key: str) -> None:
        """Delete a file from storage"""
        pass

    @abstractmethod
    def list_files(self, directory: str, include_children: bool = True) -> List[Dict]:
        """
        List files in a directory
        Returns list of dicts with 'Key' and 'LastModified' fields
        """
        pass

    @abstractmethod
    def create_directory(self, key: str) -> None:
        """Create a directory (or marker for it)"""
        pass
