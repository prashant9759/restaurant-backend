import logging
import logging.handlers
import os
from datetime import datetime
import json


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add extra fields if they exist
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id

        if hasattr(record, 'event'):
            log_entry['event'] = record.event

        if hasattr(record, 'request_data'):
            log_entry['request_data'] = record.request_data

        if hasattr(record, 'response_data'):
            log_entry['response_data'] = record.response_data

        if hasattr(record, 'processing_time'):
            log_entry['processing_time'] = record.processing_time

        if hasattr(record, 'exception'):
            log_entry['exception'] = record.exception

        if hasattr(record, 'traceback'):
            log_entry['traceback'] = record.traceback

        return json.dumps(log_entry)


def setup_logging(app):
    """Setup structured logging for the application"""

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(
        os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatters
    json_formatter = JSONFormatter()
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handlers with rotation
    # General application logs
    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(logs_dir, 'app.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(json_formatter)
    root_logger.addHandler(app_handler)

    # Error logs
    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(logs_dir, 'error.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    root_logger.addHandler(error_handler)

    # Request/Response logs
    request_handler = logging.handlers.RotatingFileHandler(
        os.path.join(logs_dir, 'requests.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    request_handler.setLevel(logging.INFO)
    request_handler.setFormatter(json_formatter)

    # Create a specific logger for requests
    request_logger = logging.getLogger('app.middleware.request_logger')
    request_logger.addHandler(request_handler)
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False  # Don't propagate to root logger

    # Database logs
    db_handler = logging.handlers.RotatingFileHandler(
        os.path.join(logs_dir, 'database.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    db_handler.setLevel(logging.INFO)
    db_handler.setFormatter(json_formatter)

    db_logger = logging.getLogger('sqlalchemy.engine')
    db_logger.addHandler(db_handler)
    db_logger.setLevel(logging.INFO)
    db_logger.propagate = False

    # Set specific loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    # Log application startup
    logger = logging.getLogger(__name__)
    logger.info("Logging system initialized", extra={
        'event': 'logging_initialized',
        'logs_directory': logs_dir
    })


def get_logger(name):
    """Get a logger instance with the given name"""
    return logging.getLogger(name)
