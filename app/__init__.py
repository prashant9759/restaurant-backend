from flask import Flask, jsonify
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException
from flask_migrate import Migrate
from flask_mail import Mail
from config import Config

import os

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
jwt = JWTManager()



def create_app(config_class=Config):

    app = Flask(__name__)
    app.config.from_object(config_class)
    
    db.init_app(app)
    migrate.init_app(app,db)
    mail.init_app(app)
    jwt.init_app(app)

    from .controllers.user import blp as UserBlp
    from .controllers.admin import blp as AdminBlp
    from .controllers.restaurant import blp as RestaurantBlp
    from .controllers.tableType import blp as tableTypeBlp
    from .controllers.tableInstance import blp as tableBlp
    from .controllers.presentation import blp as PresentationBlp
    from .controllers.user_restaurant import blp as UserRestaurantBlp
    from .controllers.adminDashboard import blp as AdminDashboardBlp
    from .controllers.food_management import blp as foodManagementBlp
    from .services.logout import is_token_revoked


    @jwt.token_in_blocklist_loader
    def check_if_token_in_blocklist(jwt_header, jwt_payload):
        return is_token_revoked(jwt_payload)


    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "message": "The token has expired.",
            "error": "token_expired"
        }), 401


    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "message": "Signature verification failed.",
            "error": "invalid_token"
        }), 401


    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "description": "Request doesn't contain an access token.",
            "error": "authorization_required"
        }), 401


    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Customize Flask error responses"""
        print(e)
        response = e.get_response()
        print(response)
        response.data = jsonify({
            "code": e.code,
            "status": e.name,
            "message": e.description if isinstance(e.description, str) else e.description.get("message"),
        }).data
        response.content_type = "application/json"
        print(response.data)
        return response


    api = Api(app)
    api.register_blueprint(UserBlp)
    api.register_blueprint(AdminBlp)
    api.register_blueprint(RestaurantBlp)
    api.register_blueprint(tableTypeBlp)
    api.register_blueprint(tableBlp)
    api.register_blueprint(PresentationBlp)
    api.register_blueprint(UserRestaurantBlp)
    api.register_blueprint(AdminDashboardBlp)
    api.register_blueprint(foodManagementBlp)


    @app.route('/')
    def home():
        return jsonify({"message": "Welcome to the Restaurant Management API!"})
    
    return app



