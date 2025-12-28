"""
Database connection module for MongoDB/DocumentDB
Handles connection to local MongoDB (dev) or AWS DocumentDB (production)
"""
from pymongo import MongoClient
from pymongo.database import Database
from flask import current_app, g
import logging
import certifi

_client = None
logger = logging.getLogger(__name__)

def get_db_client() -> MongoClient:
    """
    Get MongoDB client singleton.
    Creates a new client if one doesn't exist.
    """
    global _client
    if _client is None:
        database_url = current_app.config['DATABASE_URL']

        # For local MongoDB, use default settings
        try:
            if 'localhost' in database_url or '127.0.0.1' in database_url:
                _client = MongoClient(database_url)
            else:
                # For DocumentDB/Atlas, use TLS with certificate verification
                _client = MongoClient(
                    database_url,
                    tls=True,
                    tlsCAFile=certifi.where(),  # Use certifi bundle for TLS
                    retryWrites=False  # DocumentDB doesn't support retryable writes
                )
            if _client is not None:
                host, port = _client.address
                logger.info(
                    "MongoDB client initialized",
                    extra={"db_host": host, "db_port": port},
                )
        except Exception:
            logger.exception(
                "Failed to initialize MongoDB client",
                extra={"database_url_redacted": redact_connection_string(database_url)},
            )
            raise
    return _client

def get_db() -> Database:
    """
    Get database instance for the current request.
    Uses Flask's g object to store per-request database connection.
    """
    if 'db' not in g:
        client = get_db_client()
        g.db = client[current_app.config['DATABASE_NAME']]
    return g.db

def close_db(e=None):
    """
    Close database connection.
    This is called automatically at the end of each request.
    """
    db = g.pop('db', None)
    # Note: We don't close the client here as it's a singleton
    # The client will be closed when the application shuts down

def init_db(app):
    """
    Initialize database with Flask app.
    Registers teardown handler to close connections.
    """
    app.teardown_appcontext(close_db)
def redact_connection_string(uri: str) -> str:
    """Remove credentials from a MongoDB URI for safe logging."""
    if "@" not in uri:
        return uri
    prefix, rest = uri.split("@", 1)
    if "://" in prefix:
        scheme, _ = prefix.split("://", 1)
        return f"{scheme}://***:***@{rest}"
    return f"***:***@{rest}"
