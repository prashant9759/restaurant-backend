# Middleware package

from .error_handler import init_error_handler
from .request_logger import init_request_logger
from .logging_config import setup_logging, get_logger
from .utils import log_function_call, log_database_query, log_performance_metric, get_request_summary, sanitize_data

__all__ = [
    'init_error_handler',
    'init_request_logger',
    'setup_logging',
    'get_logger',
    'log_function_call',
    'log_database_query',
    'log_performance_metric',
    'get_request_summary',
    'sanitize_data'
]


def init_middleware(app):
    """Initialize all middleware components"""

    # Setup logging first
    setup_logging(app)

    # Initialize error handler
    init_error_handler(app)

    # Initialize request logger
    init_request_logger(app)

    # Log middleware initialization
    logger = get_logger(__name__)
    logger.info("All middleware components initialized", extra={
        'event': 'middleware_initialized'
    })
