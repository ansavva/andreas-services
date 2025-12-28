import traceback
import structlog

from src.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

def log_error(error: Exception, context: str = None):
    """
    Log an error with full traceback

    Args:
        error: The exception that was raised
        context: Optional context string to help identify where the error occurred
    """
    error_message = f"Error in {context}: {str(error)}" if context else f"Error: {str(error)}"
    logger.error(error_message)
    logger.error(traceback.format_exc())
    print(error_message)
    print(traceback.format_exc())
