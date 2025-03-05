from sqlalchemy import text
from flask import Flask, jsonify
from flask_smorest import Api
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException
from flask_cors import CORS

import os
from dotenv import load_dotenv

from datetime import datetime
import pytz

from db import db


from models import CuisineType, CuisineEnum, FoodPreferenceType, FoodPreferenceEnum

from scheduler import scheduler

from controllers.user import blp as UserBlp
from controllers.admin import blp as AdminBlp
from controllers.restaurant import blp as RestaurantBlp
from controllers.tableType import blp as tableTypeBlp
from controllers.tableInstance import blp as tableBlp
from controllers.presentation import blp as PresentationBlp
from controllers.user_restaurant import blp as UserRestaurantBlp
from controllers.adminDashboard import blp as AdminDashboardBlp
import sys
from services.logout import is_token_revoked

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
cors = CORS(app)
app.config["PROPAGATE_EXCEPTIONS"] = True
app.config["API_TITLE"] = "Restaurant Table Reservation API"
app.config["API_VERSION"] = "v1"
app.config["OPENAPI_VERSION"] = "3.0.3"
app.config["OPENAPI_URL_PREFIX"] = "/"  # Ensures API docs are served
app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["DEBUG"] = True

db.init_app(app)

# Initialize JWT
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
jwt = JWTManager(app)


@jwt.additional_claims_loader
def add_claims_to_jwt(identity):
    if identity == '1':  # Admin-specific logic
        return {"isAdmin": True}
    return {"isAdmin": False}


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


@app.route('/')
def home():
    return jsonify({"message": "Welcome to the Restaurant Management API!"})


def seed_cuisines_and_food_preferences():
    # Seeding Cuisines
    for cuisine in CuisineEnum:
        existing_cuisine = CuisineType.query.filter_by(
            name=cuisine.value).first()
        if not existing_cuisine:
            new_cuisine = CuisineType(name=cuisine.value)
            db.session.add(new_cuisine)
            # print(f"Added Cuisine: {cuisine.value}")
        # else:
        #     print(f"Already exists: {cuisine.value}")

    # Seeding Food Preferences
    for preference in FoodPreferenceEnum:
        existing_preference = FoodPreferenceType.query.filter_by(
            name=preference.value).first()
        if not existing_preference:
            new_preference = FoodPreferenceType(name=preference.value)
            db.session.add(new_preference)
            # print(f"Added Food Preference: {preference.value}")
        # else:
        #     print(f"Already exists: {preference.value}")

    # Commit changes
    try:
        db.session.commit()
        # print("✅ All cuisines and food preferences seeded successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error seeding cuisines and food preferences: {e}")


# def drop_all_tables():
#     """Drops all tables in the database irrespective of foreign keys."""
#     db.session.commit()  # Ensure all pending transactions are committed

#     with db.engine.connect() as connection:
#         connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))  # ✅ Use text()

#     db.reflect()  # Reflect all tables from the database
#     db.drop_all()  # Drop all tables

#     with db.engine.connect() as connection:
#         connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))  # ✅ Use text()

#     print("All tables dropped successfully!")




port = int(os.getenv("PORT", 5000))  # Default to 5000 if PORT is not set

print("Api running on port : {} ".format(port))

if __name__ == '__main__':
    with app.app_context():
        scheduler.start()
        db.create_all()
        seed_cuisines_and_food_preferences()

        app.run(host="0.0.0.0", port=port, debug=False)
