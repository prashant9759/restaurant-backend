# Middleware System

This directory contains the middleware components for the Restaurant Management API, providing global error handling, request/response logging, and structured logging capabilities.

## Components

### 1. Error Handler (`error_handler.py`)

- **Purpose**: Provides global error handling for all exceptions
- **Features**:
  - Catches all types of exceptions (HTTP, SQLAlchemy, Validation, JWT, etc.)
  - Returns consistent JSON error responses
  - Logs errors with appropriate levels (ERROR for 5xx, WARNING for 4xx)
  - Includes request context in error logs
  - Provides traceback in development mode

### 2. Request Logger (`request_logger.py`)

- **Purpose**: Logs detailed information about each request and response
- **Features**:
  - Generates unique request IDs for tracking
  - Logs request details (method, URL, headers, body, etc.)
  - Logs response details (status code, processing time, etc.)
  - Filters sensitive information (passwords, tokens, etc.)
  - Adds request ID and processing time to response headers
  - Different log levels based on response status

### 3. Logging Configuration (`logging_config.py`)

- **Purpose**: Sets up structured logging with file rotation
- **Features**:
  - JSON-formatted logs for machine readability
  - Separate log files for different purposes:
    - `app.log`: General application logs
    - `error.log`: Error logs only
    - `requests.log`: Request/response logs
    - `database.log`: Database query logs
  - Log rotation (10MB files, 5 backups)
  - Console output for development

### 4. Utilities (`utils.py`)

- **Purpose**: Helper functions for logging and debugging
- **Features**:
  - `@log_function_call`: Decorator for function call logging
  - `log_database_query()`: Database query logging
  - `log_performance_metric()`: Performance metric logging
  - `get_request_summary()`: Request summary for logging
  - `sanitize_data()`: Data sanitization for sensitive information

## Usage

### Automatic Initialization

The middleware is automatically initialized when the Flask app starts:

```python
# In app/__init__.py
from .middleware import init_middleware
init_middleware(app)
```

### Manual Usage of Utilities

```python
from app.middleware import log_function_call, log_performance_metric, get_logger

# Function call logging
@log_function_call
def my_function():
    # Your code here
    pass

# Performance logging
log_performance_metric("database_query_time", 150, "ms")

# Get logger
logger = get_logger(__name__)
logger.info("Custom log message")
```

## Log Files

The middleware creates the following log files in the `logs/` directory:

- **`app.log`**: General application logs (INFO level and above)
- **`error.log`**: Error logs only (ERROR level)
- **`requests.log`**: Request/response logs (INFO level)
- **`database.log`**: Database query logs (INFO level)

## Log Format

### JSON Log Format

```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "INFO",
  "logger": "app.middleware.request_logger",
  "message": "Request Started - ID: 550e8400-e29b-41d4-a716-446655440000",
  "module": "request_logger",
  "function": "before_request",
  "line": 25,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "event": "request_started",
  "request_data": {
    "method": "POST",
    "url": "http://localhost:5000/api/users",
    "path": "/api/users",
    "endpoint": "user.create_user",
    "remote_addr": "127.0.0.1",
    "user_agent": "Mozilla/5.0...",
    "timestamp": "2024-01-15T10:30:45.123456"
  }
}
```

### Error Response Format

```json
{
  "error": {
    "type": "Validation Error",
    "message": "Invalid email format",
    "status_code": 400,
    "timestamp": "2024-01-15T10:30:45.123456",
    "path": "/api/users",
    "method": "POST",
    "validation_errors": {
      "email": ["Invalid email format"]
    }
  }
}
```

## Response Headers

The middleware adds the following headers to all responses:

- **`X-Request-ID`**: Unique identifier for the request
- **`X-Processing-Time`**: Time taken to process the request (in seconds)

## Configuration

### Environment Variables

- `DEBUG`: Enable debug mode (includes traceback in error responses)
- `LOG_LEVEL`: Set logging level (default: INFO)

### Customization

You can customize the middleware behavior by modifying the respective files:

1. **Error Handler**: Add new exception types in `error_handler.py`
2. **Request Logger**: Modify sensitive data filters in `request_logger.py`
3. **Logging Config**: Adjust log file sizes and rotation in `logging_config.py`

## Security Features

- **Sensitive Data Filtering**: Automatically redacts sensitive information like passwords, tokens, etc.
- **Request ID Tracking**: Each request gets a unique ID for tracking and debugging
- **Structured Logging**: JSON format prevents log injection attacks
- **Error Sanitization**: Error messages are sanitized to prevent information leakage

## Monitoring and Debugging

### Request Tracking

Use the `X-Request-ID` header to track requests across logs:

```bash
grep "550e8400-e29b-41d4-a716-446655440000" logs/*.log
```

### Performance Monitoring

Monitor processing times in the `X-Processing-Time` header or in the request logs.

### Error Analysis

Check `error.log` for all application errors with full context and traceback information.
