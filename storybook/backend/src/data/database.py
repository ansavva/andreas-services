"""
Database connection module for MongoDB/DocumentDB
Handles connection to local MongoDB (dev) or AWS DocumentDB (production)
"""
from pymongo import MongoClient
from pymongo.database import Database
from flask import current_app, g
import certifi
import structlog

_client = None
logger = structlog.get_logger(__name__)

def get_db_client() -> MongoClient:
    """
    Get MongoDB client singleton.
    Creates a new client if one doesn't exist.
    """
    global _client
    if _client is None:
        database_url = current_app.config['DATABASE_URL']

        # For local MongoDB, use default settings
        logger.info(
            "Connecting to MongoDB",
            database_url_redacted=redact_connection_string(database_url),
        )
        try:
            if 'localhost' in database_url or '127.0.0.1' in database_url:
                _client = MongoClient(database_url)
            else:
                # For DocumentDB/Atlas, use TLS with certificate verification
                ca_path = certifi.where()
                _client = MongoClient(
                    database_url,
                    tls=True,
                    tlsCAFile=ca_path,  # Use certifi bundle for TLS
                    retryWrites=False,  # DocumentDB doesn't support retryable writes
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                )
                logger.info(
                    "MongoDB TLS configuration",
                    tls_ca_file=ca_path,
                )
            if _client is not None and getattr(_client, "address", None):
                host, port = _client.address
                logger.info(
                    "MongoDB client initialized",
                    db_host=host,
                    db_port=port,
                )
        except Exception:
            host_port = getattr(_client, "address", None)
            logger.exception(
                "Failed to initialize MongoDB client",
                database_url_redacted=redact_connection_string(database_url),
                db_host=host_port[0] if host_port else None,
                db_port=host_port[1] if host_port else None,
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
