import logging
import time
import json
from flask import request, g, current_app
from datetime import datetime
import uuid
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware:
    """Middleware for logging request and response details"""

    def __init__(self, app):
        self.app = app
        self.register_middleware()

    def register_middleware(self):
        """Register the middleware functions"""

        @self.app.before_request
        def before_request():
            """Log request details before processing"""
            # Generate unique request ID
            g.request_id = str(uuid.uuid4())
            g.start_time = time.time()

            # Get request details
            request_data = self._get_request_data()

            # Log request
            logger.info(
                f"Request Started - ID: {g.request_id}",
                extra={
                    'request_id': g.request_id,
                    'event': 'request_started',
                    'request_data': request_data
                }
            )

        @self.app.after_request
        def after_request(response):
            """Log response details after processing"""
            # Calculate processing time
            processing_time = time.time() - g.start_time

            # Get response details
            response_data = self._get_response_data(response)

            # Log response
            log_level = self._get_log_level(response.status_code)
            logger.log(
                log_level,
                f"Request Completed - ID: {g.request_id} - Status: {response.status_code} - Time: {processing_time:.3f}s",
                extra={
                    'request_id': g.request_id,
                    'event': 'request_completed',
                    'processing_time': processing_time,
                    'response_data': response_data
                }
            )

            # Add request ID to response headers
            response.headers['X-Request-ID'] = g.request_id
            response.headers['X-Processing-Time'] = f"{processing_time:.3f}s"

            return response

        @self.app.teardown_request
        def teardown_request(exception=None):
            """Handle any cleanup after request"""
            if exception:
                logger.error(
                    f"Request Failed - ID: {g.request_id}",
                    extra={
                        'request_id': g.request_id,
                        'event': 'request_failed',
                        'exception': str(exception),
                        'exception_type': type(exception).__name__
                    }
                )

    def _get_request_data(self):
        """Extract relevant request data for logging"""
        # Get basic request info
        request_data = {
            'method': request.method,
            'url': request.url,
            'path': request.path,
            'endpoint': request.endpoint,
            'remote_addr': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Add query parameters (filter sensitive data)
        if request.args:
            filtered_args = self._filter_sensitive_data(dict(request.args))
            request_data['query_params'] = filtered_args

        # Add request body (filter sensitive data)
        if request.is_json:
            try:
                body_data = request.get_json()
                filtered_body = self._filter_sensitive_data(body_data)
                request_data['body'] = filtered_body
            except Exception:
                request_data['body'] = 'Invalid JSON'
        elif request.form:
            filtered_form = self._filter_sensitive_data(dict(request.form))
            request_data['form_data'] = filtered_form

        # Add headers (filter sensitive data)
        headers = dict(request.headers)
        filtered_headers = self._filter_sensitive_headers(headers)
        request_data['headers'] = filtered_headers

        return request_data

    def _get_response_data(self, response):
        """Extract relevant response data for logging"""
        response_data = {
            'status_code': response.status_code,
            'status': response.status,
            'content_type': response.content_type,
            'content_length': response.content_length,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Add response headers (filter sensitive data)
        headers = dict(response.headers)
        filtered_headers = self._filter_sensitive_headers(headers)
        response_data['headers'] = filtered_headers

        # Add response body for error responses or in debug mode
        if (response.status_code >= 400 or
                current_app.config.get('DEBUG', False)):
            try:
                if response.content_type == 'application/json':
                    response_data['body'] = response.get_json()
                else:
                    response_data['body'] = response.get_data(
                        as_text=True)[:1000]  # Limit to 1000 chars
            except Exception:
                response_data['body'] = 'Unable to parse response body'

        return response_data

    def _filter_sensitive_data(self, data):
        """Filter out sensitive information from data"""
        if not isinstance(data, dict):
            return data

        sensitive_keys = {
            'password', 'token', 'secret', 'key', 'authorization',
            'auth', 'credential', 'api_key', 'access_token',
            'refresh_token', 'jwt', 'session', 'cookie'
        }

        filtered_data = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                filtered_data[key] = '***REDACTED***'
            elif isinstance(value, dict):
                filtered_data[key] = self._filter_sensitive_data(value)
            elif isinstance(value, list):
                filtered_data[key] = [
                    self._filter_sensitive_data(
                        item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                filtered_data[key] = value

        return filtered_data

    def _filter_sensitive_headers(self, headers):
        """Filter out sensitive headers"""
        sensitive_headers = {
            'authorization', 'cookie', 'x-api-key', 'x-auth-token',
            'x-access-token', 'x-refresh-token'
        }

        filtered_headers = {}
        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                filtered_headers[key] = '***REDACTED***'
            else:
                filtered_headers[key] = value

        return filtered_headers

    def _get_log_level(self, status_code):
        """Determine log level based on status code"""
        if status_code >= 500:
            return logging.ERROR
        elif status_code >= 400:
            return logging.WARNING
        else:
            return logging.INFO


def init_request_logger(app):
    """Initialize request logger middleware"""
    return RequestLoggerMiddleware(app)
