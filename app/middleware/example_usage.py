"""
Example usage of middleware utilities in controllers
This file demonstrates how to use the middleware utilities in your application
"""

from flask import request, jsonify
from flask_smorest import Blueprint
from .utils import log_function_call, log_performance_metric, get_logger, sanitize_data
from .logging_config import get_logger

# Get logger for this module
logger = get_logger(__name__)

blp = Blueprint("example", __name__, description="Example usage of middleware")


@blp.route("/api/example/function-logging")
def example_function_logging():
    """
    Example of using the @log_function_call decorator
    """
    result = process_data_with_logging()
    return jsonify({"message": "Function logged successfully", "result": result})


@log_function_call
def process_data_with_logging():
    """
    This function will be automatically logged with timing information
    """
    # Simulate some processing
    import time
    time.sleep(0.1)

    # Log some performance metrics
    log_performance_metric("data_processing_time", 100, "ms")

    return "processed_data"


@blp.route("/api/example/performance-logging")
def example_performance_logging():
    """
    Example of logging performance metrics
    """
    import time

    # Simulate database query
    start_time = time.time()
    time.sleep(0.05)  # Simulate DB query
    db_time = (time.time() - start_time) * 1000  # Convert to milliseconds

    # Log database performance
    log_performance_metric("database_query_time", db_time, "ms")

    # Simulate API call
    start_time = time.time()
    time.sleep(0.03)  # Simulate API call
    api_time = (time.time() - start_time) * 1000

    # Log API performance
    log_performance_metric("external_api_time", api_time, "ms")

    return jsonify({
        "message": "Performance metrics logged",
        "db_time": f"{db_time:.2f}ms",
        "api_time": f"{api_time:.2f}ms"
    })


@blp.route("/api/example/custom-logging")
def example_custom_logging():
    """
    Example of custom logging with request context
    """
    # Log request details
    logger.info("Processing custom logging example", extra={
        'event': 'custom_example',
        'user_agent': request.headers.get('User-Agent'),
        'ip_address': request.remote_addr
    })

    # Log with different levels
    logger.debug("Debug information")
    logger.info("Info message")
    logger.warning("Warning message")

    return jsonify({"message": "Custom logging examples completed"})


@blp.route("/api/example/data-sanitization")
def example_data_sanitization():
    """
    Example of data sanitization
    """
    # Sample data with sensitive information
    sensitive_data = {
        "user": {
            "name": "John Doe",
            "email": "john@example.com",
            "password": "secret123",
            "api_key": "sk-1234567890abcdef"
        },
        "request": {
            "token": "jwt_token_here",
            "data": "normal_data"
        }
    }

    # Sanitize the data
    sanitized_data = sanitize_data(sensitive_data)

    # Log the sanitized data (safe to log)
    logger.info("Data sanitization example", extra={
        'event': 'data_sanitization',
        'original_keys': list(sensitive_data.keys()),
        'sanitized_data': sanitized_data
    })

    return jsonify({
        "message": "Data sanitization example",
        "sanitized_data": sanitized_data
    })


@blp.route("/api/example/error-logging")
def example_error_logging():
    """
    Example of error logging (this will trigger the error handler)
    """
    # This will be caught by the global error handler
    raise ValueError("This is an example error for testing error logging")


@blp.route("/api/example/validation-error")
def example_validation_error():
    """
    Example of validation error (this will be caught by the error handler)
    """
    from marshmallow import ValidationError

    # This will be caught by the global error handler
    raise ValidationError("Invalid data format", field_name="email")
