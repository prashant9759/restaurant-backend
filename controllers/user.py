from urllib import response

from flask import request
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required,get_jwt
from sqlalchemy.orm import load_only, noload,joinedload

from sqlalchemy import exists
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from passlib.hash import pbkdf2_sha256

from models import User, Restaurant, RestaurantLike, RestaurantReview
from db import db
from schemas import UserSchema, LoginSchema, ChangePasswordSchema, RestaurantReviewSchema   
from services.logout import logout_logic
from services.helper import *

from datetime import datetime


blp = Blueprint("Users", __name__, description="Operations on users")

# Business Logic Functions

def check_user_role():
    """Check if the JWT contains the 'user' role."""
    claims = get_jwt()
    if claims.get("role") != "user":
        abort(403, message="Access forbidden: User role required.")



# API Routes
@blp.route("/api/users")
class UserList(MethodView):
    @blp.arguments(UserSchema)
    def post(self, user_data):
        """Create a new user and return the created user with tokens."""
        print("user creation called")
        # Check if an ACTIVE user already exists with the same email or phone
        existing_user = User.query.filter(
            (User.email == user_data["email"]) | (User.phone == user_data.get("phone")),
            User.is_deleted == False
        ).first()

        if existing_user:
            return {"message": "Email or phone already in use"}, 400  # Prevent duplicate active users
        user_data.pop("confirm_password")
        return create_logic(user_data, User, "user")

    @jwt_required()
    def get(self):
        """Get the current user using the token."""
        check_user_role()  # Ensure only users can access this
        user_id = get_jwt_identity()
        user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
        return user


    @jwt_required()
    @blp.arguments(UserSchema(partial=True))
    def patch(self, user_data):
        """Update the current user (PATCH, partial update)."""
        check_user_role()
        user_id = get_jwt_identity()
        user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()

        return update_logic(user, user_data, "user")

    @jwt_required()
    @blp.response(204)
    def delete(self):
        """Delete the current user."""
        check_user_role()
        user_id = get_jwt_identity()
        user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
        try:
            jti = get_jwt()["jti"]
            exp = get_jwt()["exp"] 
            logout_logic(jti,exp)
            user.soft_delete()
            return {"message": "User deleted succefully", "status":204}, 204
        except Exception as e:
            db.session.rollback()  # Rollback in case of failure
            return {"message": "Failed to delete user", "error": str(e)}, 500

@blp.route("/api/users/change-password", methods=["POST"])
@jwt_required()
@blp.arguments(ChangePasswordSchema)  
def change_password(data):
    check_user_role()
    user_id = get_jwt_identity()
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    return update_password(user,data)

@blp.route("/api/users/all")
class AllUsers(MethodView):
    def get(self):
        """Get all users without any authentication."""
        return get_all_item_logic(User, "user")
    
    

@blp.route("/api/users/login")
class UserLogin(MethodView):
    @blp.arguments(LoginSchema)
    def post(self, user_data):
        """Log in a user and return access and refresh tokens."""
        return login_logic(user_data, User, "user")


@blp.route("/api/users/logout")
class UserLogout(MethodView):
    @jwt_required()
    def post(self):
        """Log out the current user."""
        jti = get_jwt()["jti"]
        exp = get_jwt()["exp"]  # Token expiration timestamp
        return logout_logic(jti, exp)