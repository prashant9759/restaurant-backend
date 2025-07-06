import time
import functools
from flask import g, request
from .logging_config import get_logger

logger = get_logger(__name__)


def log_function_call(func):
    """Decorator to log function calls with timing"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()

        # Get function info
        func_name = func.__name__
        module_name = func.__module__

        # Log function entry
        logger.debug(
            f"Function called: {module_name}.{func_name}",
            extra={
                'event': 'function_entry',
                'function': f"{module_name}.{func_name}",
                'args_count': len(args),
                'kwargs_count': len(kwargs),
                'request_id': getattr(g, 'request_id', None)
            }
        )

        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Log successful completion
            logger.debug(
                f"Function completed: {module_name}.{func_name} in {execution_time:.3f}s",
                extra={
                    'event': 'function_exit',
                    'function': f"{module_name}.{func_name}",
                    'execution_time': execution_time,
                    'status': 'success',
                    'request_id': getattr(g, 'request_id', None)
                }
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time

            # Log error
            logger.error(
                f"Function failed: {module_name}.{func_name} after {execution_time:.3f}s",
                extra={
                    'event': 'function_error',
                    'function': f"{module_name}.{func_name}",
                    'execution_time': execution_time,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'request_id': getattr(g, 'request_id', None)
                }
            )
            raise

    return wrapper


def log_database_query(query, params=None):
    """Log database query for debugging"""
    logger.debug(
        "Database query executed",
        extra={
            'event': 'database_query',
            'query': str(query),
            'params': params,
            'request_id': getattr(g, 'request_id', None)
        }
    )


def log_performance_metric(metric_name, value, unit='ms'):
    """Log performance metrics"""
    logger.info(
        f"Performance metric: {metric_name} = {value}{unit}",
        extra={
            'event': 'performance_metric',
            'metric_name': metric_name,
            'value': value,
            'unit': unit,
            'request_id': getattr(g, 'request_id', None)
        }
    )


def get_request_summary():
    """Get a summary of the current request for logging"""
    if not request:
        return None

    return {
        'method': request.method,
        'url': request.url,
        'path': request.path,
        'endpoint': request.endpoint,
        'remote_addr': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'content_type': request.content_type,
        'content_length': request.content_length,
        'request_id': getattr(g, 'request_id', None)
    }


def sanitize_data(data, sensitive_keys=None):
    """Sanitize data by removing sensitive information"""
    if sensitive_keys is None:
        sensitive_keys = {
            'password', 'token', 'secret', 'key', 'authorization',
            'auth', 'credential', 'api_key', 'access_token',
            'refresh_token', 'jwt', 'session', 'cookie'
        }

    if not isinstance(data, dict):
        return data

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = '***REDACTED***'
        elif isinstance(value, dict):
            sanitized[key] = sanitize_data(value, sensitive_keys)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_data(item, sensitive_keys) if isinstance(
                    item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized
