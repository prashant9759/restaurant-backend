from app.models import  *
from app import db
from app.schemas import WEEKDAYS

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token
)
from passlib.hash import pbkdf2_sha256
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_smorest import abort

from datetime import datetime, timedelta,time


def verify_email_verification_code(Model,model_name,data):
    email = data["email"]
    code = data["verification_code"]
    # Start building the query
    query = Model.query.filter_by(email=email, is_deleted=False)

    # If restaurant_id is in data, add it to the query filter
    if "restaurant_id" in data:
        query = query.filter_by(restaurant_id=data["restaurant_id"])
    
    if "role" in data:
        query = query.filter_by(role=data["role"])

    item = query.first()
    if not item:
        return {"message": f"{model_name.upper()} not found."}, 404
    if item.is_email_verified:
        return {"message": "Email already verified."}, 400
    if item.email_verification_code != code:
        return {"message": "Invalid verification code."}, 400
    # Check expiry (10 minutes)
    expiry_time = item.verification_code_sent_at + timedelta(minutes=10)
    if datetime.utcnow() > expiry_time:
        return {"message": "Verification code has expired."}, 400
    # Update verification status
    item.is_email_verified = True
    item.email_verification_code = None
    db.session.commit()
    # Generate tokens
    role = model_name
    if "role" in data:
        role = data["role"]
    access_token = create_access_token(identity=str(item.id), additional_claims={"role": f"{role}"}, fresh=True)
    refresh_token = create_refresh_token(identity=str(item.id),additional_claims={"role": f"{role}"})
    return {
                "message": "Email verified successfully.",
                "access_token":access_token,
                "refresh_token":refresh_token
        }, 200



def generate_time_slots(opening_time, closing_time, reservation_duration):
    slots = []
    
    # Convert opening_time & closing_time to datetime for arithmetic operations
    current_time = datetime.combine(datetime.today(), opening_time)
    closing_datetime = datetime.combine(datetime.today(), closing_time)

    while current_time + timedelta(minutes=reservation_duration) <= closing_datetime:
        slots.append(current_time.strftime("%H:%M"))  # Format as HH:MM
        current_time += timedelta(minutes=reservation_duration)  # Move to next slot

    return slots

# Create a new entry and generate tokens   
def create_logic(data, Model, entity, extra_msg=""):
    """Business logic to create a new entry"""
    
    
    data["password"] = pbkdf2_sha256.hash(data["password"])
    item = Model(**data)
    
    try:
        db.session.add(item)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        print(e.orig)
        if "email" in str(e.orig):
            abort(400, message=f"{entity} with this email already exists.")
        elif "name" in str(e.orig):
            abort(400, message=f"{entity} with this name already exists.")
        elif "phone" in str(e.orig):
            abort(400, message=f"{entity} with this phone number already exists.")
        else:
            abort(500, message=f"{e.orig}")
    except SQLAlchemyError as e:
        db.session.rollback()
        print("error",e)
        abort(500, message=f"An error occurred while creating the entity.")
    
    return {
        f"{entity}": item.to_dict(),
        "message": f"{entity.capitalize()} created successfully"+extra_msg,
        "status": 201
    } , 201


# Fetch all items from the database

def get_all_item_logic(Model, entity):
    """Fetch all items from the database."""
    items = Model.query.filter_by(is_deleted=False).all()
    return {f"{entity}s": [item.to_dict() for item in items], "message":f"all {entity}s fetched successfully", "status":200}, 200
  

# Fetch an item by ID

def get_item_by_id_logic(id, Model, entity):
    """Fetch an item by ID."""
    item = Model.query.get(id)
    if not item:
        return abort(404, message=f"{entity} not found.")
    return {f"{entity}": item.to_dict(), "message": f"{entity} fetched successfully", "status": 200}, 200
 



def update_logic(item, data, entity, extra_msg=""):
    try:
        # Dynamically update fields based on model attributes
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return {
            f"{entity}": item.to_dict(),
            "message": f"{entity.capitalize()} updated successfully"+extra_msg,
            "status": 200
        }, 200

    except IntegrityError as e:
        db.session.rollback()
        error_message = str(e.orig)

        if "email" in error_message:
            return abort(400, message=f"A {entity} with this email already exists")
        elif "name" in error_message:
            return abort(400, message=f"A {entity} with this name already exists")
        elif "phone" in error_message:
            return abort(400, message=f"A {entity} with this phone number already exists")
        else:
            abort(500, message=f"An error occurred while updating the {entity}.")

 
# Login a user

def login_logic(login_data, Model, entity):
    """Business logic to log in a user."""
    query = Model.query.filter_by(
        email=login_data["email"],is_deleted=False
        )
    
    if "restaurant_id" in login_data:
        # .filter() is better here to combine with existing filters
        query = query.filter(Model.restaurant_id == login_data["restaurant_id"])
        
    if 'role' in login_data:
        query = query.filter(Model.role == login_data["role"])
        
    item = query.first_or_404()
    
    if not item.is_email_verified:
        abort(400, message="Email not verified")
    
    if not item or not pbkdf2_sha256.verify(login_data["password"], item.password):
        return abort(401, message="Invalid email or password.")
    
    role = entity
    if "role" in login_data:
        role = login_data["role"]
    
    access_token = create_access_token(identity=str(item.id), additional_claims={"role": f"{role}"}, fresh=True)
    refresh_token = create_refresh_token(identity=str(item.id),additional_claims={"role": f"{role}"})
    
    return {
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "status": 200
    }, 200

# Delete an item

def delete_logic(id, Model, entity):
    """Delete an item."""
    item = Model.query.get(id)
    if not item:
        return abort(404, message=f"{entity} not found.")
    
    db.session.delete(item)
    db.session.commit()
    return {"message": f"{entity} deleted successfully", "status": 204}, 204


# update password
def update_password(item,data):
    # Check if current password is correct
    try:
        if not item or not pbkdf2_sha256.verify(data["current_password"], item.password):
            return { "message":"Wrong password Provided.","status":401},401

        # Update password
        item.password = pbkdf2_sha256.hash(data["new_password"])
        db.session.commit()

        return {"message": "Password updated successfully!"}, 200
    
    except Exception as e:
        db.session.rollback()  # Rollback in case of failure
        return {"error": str(e)}, 500  # Generic error handling


def get_opening_closing_time(date_obj, operating_hours):
    # Step 1: Get the day name
    day_name = date_obj.strftime("%A")  # e.g., 'Monday'
    day_no = WEEKDAYS[day_name]

    # Step 2: Find opening and closing times
    for day_info in operating_hours:
        if day_info.day_of_week == day_no:
            return day_info.opening_time, day_info.closing_time

    
    # If not found
    return None, None



