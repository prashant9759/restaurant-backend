import traceback
import logging
from flask import jsonify, request, current_app
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from marshmallow import ValidationError
from flask_jwt_extended.exceptions import JWTExtendedException
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware:
    """Global error handler middleware for consistent error responses"""

    def __init__(self, app):
        self.app = app
        self.register_error_handlers()

    def register_error_handlers(self):
        """Register all error handlers"""

        @self.app.errorhandler(Exception)
        def handle_generic_exception(e):
            """Handle all unhandled exceptions"""
            return self._handle_exception(e, 500, "Internal Server Error")

        @self.app.errorhandler(HTTPException)
        def handle_http_exception(e):
            """Handle HTTP exceptions"""
            return self._handle_exception(e, e.code, e.name)

        @self.app.errorhandler(SQLAlchemyError)
        def handle_sqlalchemy_error(e):
            """Handle database-related errors"""
            return self._handle_exception(e, 500, "Database Error")

        @self.app.errorhandler(ValidationError)
        def handle_validation_error(e):
            """Handle validation errors from marshmallow"""
            return self._handle_exception(e, 400, "Validation Error")

        @self.app.errorhandler(JWTExtendedException)
        def handle_jwt_error(e):
            """Handle JWT-related errors"""
            return self._handle_exception(e, 401, "Authentication Error")

        @self.app.errorhandler(ValueError)
        def handle_value_error(e):
            """Handle value errors"""
            return self._handle_exception(e, 400, "Bad Request")

        @self.app.errorhandler(KeyError)
        def handle_key_error(e):
            """Handle key errors"""
            return self._handle_exception(e, 400, "Missing Required Field")

        @self.app.errorhandler(TypeError)
        def handle_type_error(e):
            """Handle type errors"""
            return self._handle_exception(e, 400, "Invalid Data Type")

    def _handle_exception(self, exception, status_code, error_type):
        """Common exception handler"""

        # Get request information
        request_info = {
            'method': request.method,
            'url': request.url,
            'headers': dict(request.headers),
            'args': dict(request.args),
            'json': request.get_json(silent=True),
            'timestamp': datetime.utcnow().isoformat()
        }

        # Prepare error response
        error_response = {
            'error': {
                'type': error_type,
                'message': str(exception),
                'status_code': status_code,
                'timestamp': datetime.utcnow().isoformat(),
                'path': request.path,
                'method': request.method
            }
        }

        # Add validation errors if it's a ValidationError
        if isinstance(exception, ValidationError):
            error_response['error']['validation_errors'] = exception.messages

        # Log the error with different levels based on status code
        if status_code >= 500:
            logger.error(
                f"Server Error: {error_type} - {str(exception)}",
                extra={
                    'request_info': request_info,
                    'exception': exception,
                    'traceback': traceback.format_exc()
                }
            )
        elif status_code >= 400:
            logger.warning(
                f"Client Error: {error_type} - {str(exception)}",
                extra={
                    'request_info': request_info,
                    'exception': exception
                }
            )
        else:
            logger.info(
                f"Application Error: {error_type} - {str(exception)}",
                extra={
                    'request_info': request_info,
                    'exception': exception
                }
            )

        # In development mode, include traceback
        if current_app.config.get('DEBUG', False):
            error_response['error']['traceback'] = traceback.format_exc()

        return jsonify(error_response), status_code


def init_error_handler(app):
    """Initialize error handler middleware"""
    return ErrorHandlerMiddleware(app)
