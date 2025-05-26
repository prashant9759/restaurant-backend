import os
from dotenv import load_dotenv
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    PROPAGATE_EXCEPTIONS = True
    API_TITLE = "Restaurant Table Reservation API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/swagger-ui"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'jsdnkjcnwhf3wyr8y34ferfbehrv'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get(
        'MAIL_USE_TLS', 'True').lower() in ['true', '1']
    MAIL_USE_SSL = os.environ.get(
        'MAIL_USE_SSL', 'False').lower() in ['true', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')

    ADMINS = ['prashantkumar.20255@gmail.com']

    # Celery Configuration
    CELERY_CONFIG = {
        'broker_url': 'redis://localhost:6379/0',
        'result_backend': 'redis://localhost:6379/0',
        'broker_transport_options': {
            'visibility_timeout': 3600
        }
    }
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    CELERY_ENABLE_UTC = True
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_BROKER_CONNECTION_MAX_RETRIES = 10
    CELERY_BROKER_CONNECTION_RETRY = True


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///dev.db')


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Use in-memory SQLite database
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    JWT_SECRET_KEY = 'testing-secret-key'
    PRESERVE_CONTEXT_ON_EXCEPTION = False  # Don't preserve context on exception
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': None,  # Disable connection pooling for tests
        'pool_pre_ping': False  # Disable connection health checks
    }


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
