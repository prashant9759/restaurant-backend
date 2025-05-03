from urllib import response
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import  get_jwt_identity, jwt_required,get_jwt

from flask import current_app, request
from app.models import User
from app import db
from app.schemas import (
    UserSchema, UserLoginSchema, 
    ChangePasswordSchema ,
    UserEmailVerificationSchema
) 
from app.services.logout import logout_logic
from app.services.helper import *
from app.services.email import send_email
import random
import string




blp = Blueprint("Users", __name__, description="Operations on users")

# Business Logic Functions

def check_user_role():
    """Check if the JWT contains the 'user' or 'staff' role."""
    claims = get_jwt()
    if claims.get("role") not in  ["user", "staff"]:
        abort(403, message="Access forbidden: Invalid  role")


@blp.route("/api/users")
class UserList(MethodView):
    @blp.arguments(UserSchema)
    def post(self, user_data):
        """Create a new user and send an email verification code."""
        existing_user = User.query.filter(
            (User.email == user_data["email"]) | (User.phone == user_data.get("phone")),
            User.is_deleted == False,
            User.restaurant_id == user_data["restaurant_id"],
            User.role == user_data["role"]
        ).first()

        restaurant = Restaurant.query.filter(Restaurant.id==user_data["restaurant_id"]).first()
        
        if not restaurant:
            abort(404,message="Restaurant not found")

        if existing_user:
            return {"message": "Email or phone already in use."}, 400


        # Remove confirmation field
        user_data.pop("confirm_password")

        # Generate verification code
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        user_data["email_verification_code"] = verification_code
        user_data["is_email_verified"] = False  # Default
        user_data["verification_code_sent_at"] = datetime.utcnow()

        # Create the user
        response = create_logic(user_data, User, "user",
            "\n Please verify your email address by checking your inbox for the verification code."
        )

        # Send verification email
        verification_text = f"Your verification code is: {user_data['email_verification_code']}. This code will expire in 10 minutes."
        send_email(
            subject="Verify your email address",
            sender=current_app.config['ADMINS'][0],
            recipients=[user_data["email"]],
            text_body=verification_text
        )

        return response

        

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
        
        if "confirm_password" in user_data:
            user_data.pop("confirm_password")
        if "password" in user_data:
            user_data.pop("password")
        if "restaurant_id" in user_data:
            user_data.pop("restaurant_id")
        if 'role' in user_data:
            user_data.pop('role')
        
        extra_msg=""
        email_changed=False

        # Check if email is present and already used by another user
        if 'email' in user_data:
            if user.email != user_data['email']:
                email_changed=True
            existing_email_user = User.query.filter(
                User.email == user_data['email'],
                User.id != user_id,
                User.is_deleted == False
            ).first()
            if existing_email_user:
                abort(400, message="Email is already in use by another user.")

        # Check if phone is present and already used by another user
        if 'phone' in user_data:
            existing_phone_user = User.query.filter(
                User.phone == user_data['phone'],
                User.id != user_id,
                User.is_deleted == False
            ).first()
            if existing_phone_user:
                abort(400, message="Phone number is already in use by another user.")
                
        if email_changed:
            extra_msg = "\n Please verify your email address by checking your inbox for the verification code."
            # Generate verification code
            verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            user_data["email_verification_code"] = verification_code
            user_data["is_email_verified"] = False  # Default
            user_data["verification_code_sent_at"] = datetime.utcnow()

        response = update_logic(user, user_data, "user", extra_msg)
        
        if email_changed:
            # Send verification email
            verification_text = f"Your verification code is: {user_data['email_verification_code']}. This code will expire in 10 minutes."
            send_email(
                subject="Verify your email address",
                sender=current_app.config['ADMINS'][0],
                recipients=[user_data["email"]],
                text_body=verification_text
            )

            
        return response
            
            


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


@blp.route("/api/users/verify-email")
class UserEmailVerification(MethodView):
    @blp.arguments(UserEmailVerificationSchema)
    def post(self, data):
        """Verify user's email using the verification code."""
        return verify_email_verification_code(User,"user",data)


@blp.route("/api/users/resend-email-verification")
class ResendEmailVerification(MethodView):
    def get(self):
        email = request.args.get("email")
        restaurant_id = request.args.get("restaurant_id")
        role = request.args.get("role")

        if not email:
            return {"message": "Email is required."}, 400
        
        if not restaurant_id:
            abort(400, message="Restaurant Id is required")
            
        if not role:
            abort(400, message="Role field is required")

        query = User.query.filter_by(email=email, is_deleted=False,role=role)
            
        query = query.filter_by(restaurant_id=restaurant_id)

        user = query.first()

        if not user:
            return {"message": "User not found."}, 404
        if user.is_email_verified:
            return {"message": "Email is already verified."}, 400

        # Generate verification code
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        user.email_verification_code = verification_code
        user.is_email_verified = False  # Default
        user.verification_code_sent_at = datetime.utcnow()
        db.session.commit()
        
        verification_text = f"Your verification code is: {verification_code}. This code will expire in 10 minutes."
        
        send_email(
            subject="Reverify your email address",
            sender=current_app.config['ADMINS'][0],
            recipients=[email],
            text_body=verification_text
        )

        return {"message": "Verification code resent successfully, plz check your inbox for the same."}, 200



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
    @blp.arguments(UserLoginSchema)
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