from flask import request
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import  get_jwt_identity, jwt_required, get_jwt

from flask import current_app
from app.models import Admin
from app.schemas import (
    AdminSchema, AdminLoginSchema, 
    ChangePasswordSchema,
    AdminEmailVerificationSchema
)
from app.services.logout import logout_logic
from app.services.helper import *
from app.services.email import send_email
import random
import string

blp = Blueprint("Admins", __name__, description="Operations on admins")

# Business Logic Functions

def check_admin_role():
    """Check if the JWT contains the 'admin' role."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")

# API Routes

@blp.route("/api/admins")
class AdminList(MethodView):
    @blp.arguments(AdminSchema)
    def post(self, admin_data):
        """Create a new admin and return the created admin with tokens."""
        existing_admin = Admin.query.filter(
            (Admin.email == admin_data["email"]) | (Admin.phone == admin_data.get("phone")),
            Admin.is_deleted == False
        ).first()


        if existing_admin:
            return {"message": "Email or phone already in use."}, 400


        # Remove confirmation field
        admin_data.pop("confirm_password")

        # Generate verification code
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        admin_data["email_verification_code"] = verification_code
        admin_data["is_email_verified"] = False  # Default
        admin_data["verification_code_sent_at"] = datetime.utcnow()

        # Create the user
        response = create_logic(admin_data, Admin, "admin",
            "\n Please verify your email address by checking your inbox for the verification code."
        )

        # Send verification email
        verification_text = f"Your verification code is: {admin_data['email_verification_code']}. This code will expire in 10 minutes."
        send_email(
            subject="Verify your email address",
            sender=current_app.config['ADMINS'][0],
            recipients=[admin_data["email"]],
            text_body=verification_text
        )

        return response

    @jwt_required()
    def get(self):
        """Get the current admin using the token."""
        check_admin_role()  # Ensure only admins can access this
        admin_id = get_jwt_identity()
        return get_item_by_id_logic(admin_id, Admin, "admin")

    @jwt_required()
    @blp.arguments(AdminSchema(partial=True))
    def patch(self, admin_data):
        """Update the current admin (PATCH, partial update)."""
        check_admin_role()
        admin_id = get_jwt_identity()
        admin = Admin.query.filter_by(id=admin_id, is_deleted=False).first_or_404()
        
        if "confirm_password" in admin_data:
            admin_data.pop("confirm_password")
        if "password" in admin_data:
            admin_data.pop("password")
        
        extra_msg=""
        email_changed=False

        # Check if email is present and already used by another user
        if 'email' in admin_data:
            if admin.email != admin_data['email']:
                email_changed=True
            existing_email_user = Admin.query.filter(
                Admin.email == admin_data['email'],
                Admin.id != admin_id,
                Admin.is_deleted == False
            ).first()
            if existing_email_user:
                abort(400, message="Email is already in use by another admin.")

        # Check if phone is present and already used by another user
        if 'phone' in admin_data:
            existing_phone_admin = Admin.query.filter(
                Admin.phone == admin_data['phone'],
                Admin.id != admin_id,
                Admin.is_deleted == False
            ).first()
            if existing_phone_admin:
                abort(400, message="Phone number is already in use by another admin.")
                
        if email_changed:
            extra_msg = "\n Please verify your email address by checking your inbox for the verification code."
            # Generate verification code
            verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            admin_data["email_verification_code"] = verification_code
            admin_data["is_email_verified"] = False  # Default
            admin_data["verification_code_sent_at"] = datetime.utcnow()

        response = update_logic(admin,admin_data, "admin", extra_msg)
        
        if email_changed:
            # Send verification email
            verification_text = f"Your verification code is: {admin_data['email_verification_code']}. This code will expire in 10 minutes."
            send_email(
                subject="Verify your email address",
                sender=current_app.config['ADMINS'][0],
                recipients=[admin_data["email"]],
                text_body=verification_text
            )

            
        return response



@blp.route("/api/admins/verify-email")
class AdminEmailVerification(MethodView):
    @blp.arguments(AdminEmailVerificationSchema)
    def post(self, data):
        """Verify admin's email using the verification code."""
        return verify_email_verification_code(Admin,"admin",data)


@blp.route("/api/admins/resend-email-verification")
class ResendEmailVerification(MethodView):
    def get(self):
        email = request.args.get("email")
        
        if not email:
            return {"message": "Email is required."}, 400

        query = Admin.query.filter_by(email=email, is_deleted=False)

        admin = query.first()

        if not admin:
            return {"message": "Admin not found."}, 404
        if admin.is_email_verified:
            return {"message": "Email is already verified."}, 400

        # Generate and save a new code
        verification_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        admin.email_verification_code = verification_code
        admin.is_email_verified = False  # Default
        admin.verification_code_sent_at = datetime.utcnow()
        db.session.commit()

        verification_text = f"Your verification code is: {verification_code}. This code will expire in 10 minutes."
        
        send_email(
            subject="Reverify your email address",
            sender=current_app.config['ADMINS'][0],
            recipients=[email],
            text_body=verification_text
        )

        return {"message": "Verification code resent successfully please check your inbox for the same."}, 200



@blp.route("/api/admins/all")
class AllAdmins(MethodView):
    def get(self):
        """Get all admins without any authentication."""
        return get_all_item_logic(Admin, "admin")
    
    
@blp.route("/api/admins/change-password", methods=["POST"])
@jwt_required()
@blp.arguments(ChangePasswordSchema)  
def change_password(data):
    check_admin_role()
    user_id = get_jwt_identity()
    admin = Admin.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    return update_password(admin,data)
    

@blp.route("/api/admins/login")
class AdminLogin(MethodView):
    @blp.arguments(AdminLoginSchema)
    def post(self, admin_data):
        """Log in an admin and return access and refresh tokens."""
        
        return login_logic(admin_data, Admin, "admin")

@blp.route("/api/admins/logout")
class AdminLogout(MethodView):
    @jwt_required()
    def post(self):
        """Log out the current admin."""
        jti = get_jwt()["jti"]
        exp = get_jwt()["exp"]  # Token expiration timestamp
        return logout_logic(jti, exp)
