from models import  *
from db import db

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token
)
from passlib.hash import pbkdf2_sha256
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from flask_smorest import abort
from math import radians, sin, cos, sqrt, atan2

from datetime import datetime, timedelta,time

# Business Logic Functions for CRUD operations




def generate_time_slots(opening_time, closing_time, reservation_duration):
    slots = []
    
    # Convert opening_time & closing_time to datetime for arithmetic operations
    current_time = datetime.combine(datetime.today(), opening_time)
    closing_datetime = datetime.combine(datetime.today(), closing_time)

    while current_time + timedelta(minutes=reservation_duration) <= closing_datetime:
        slots.append(current_time.strftime("%H:%M"))  # Format as HH:MM
        current_time += timedelta(minutes=reservation_duration)  # Move to next slot

    return slots

# 
def manage_address_field(data):
    # Extract address data from hospital_data
    address = data.pop("address")

    # Create and save the address in the Address table
    city_state = CityStateModel.query.filter_by(
        postal_code=address["postal_code"]
    ).first()
    if not city_state:
        city_state = CityStateModel(
        city=address["city"],
        state=address["state"],
        postal_code=address["postal_code"]
    )
    field = {"city_state": city_state,"street": address["street"],"latitude":                               address["latitude"],"longitude": address["longitude"]}
    return field

# Create a new entry and generate tokens   
def create_logic(data, Model, entity):
    """Business logic to create a new entry and generate tokens."""
    
    field = {}
    
    if 'address' in data:
        # Extract address data from hospital_data
        field = manage_address_field(data)
    
    data["password"] = pbkdf2_sha256.hash(data["password"])
    item = Model(**data, **field)
    
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
    
    # Generate tokens
    access_token = create_access_token(identity=str(item.id), additional_claims={"role": f"{entity}"}, fresh=True)
    refresh_token = create_refresh_token(identity=str(item.id),additional_claims={"role": f"{entity}"})
    
    return {
        f"{entity}": item.to_dict(),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "message": f"{entity.capitalize()} created successfully",
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
 
# Update an item & address

def update_address(item, data, entity):
    try:
        item.street = data.get("street", item.street)
        item.latitude = data.get("latitude", item.latitude)
        item.longitude = data.get("longitude", item.longitude)

        # Update or create CityStateModel and assign it directly
        city_state = CityStateModel.query.filter_by(postal_code=data["postal_code"]).first()
        if not city_state:
            city_state = CityStateModel(
                city=data['city'],
                state=data['state'],
                postal_code=data["postal_code"]
            )
            db.session.add(city_state)  # Add new city_state to session
        
        
        item.city_state = city_state  # Assign the object directly
        db.session.commit()

        return {
            "address": {
                "street": item.street,
                "latitude": item.latitude,
                "longitude": item.longitude,
                "city": item.city_state.city if item.city_state else None,
                "state": item.city_state.state if item.city_state else None,
                "postal_code": item.city_state.postal_code if item.city_state else None
            },
            "message": f"{entity.capitalize()}'s address updated successfully",
            "status": 200
        }, 200

    except Exception as e:  # Catch exceptions properly
        db.session.rollback()  # Rollback in case of error
        abort(500, message=f"An error occurred while updating the address of {entity}. Error: {str(e)}")



def update_logic(item, data, entity):
    try:
        # Dynamically update fields based on model attributes
        for key, value in data.items():
            if key == "shape":
                setattr(item, key, TableShape(value)) 
            elif hasattr(item, key):
                setattr(item, key, value)

        db.session.commit()
        return {
            f"{entity}": item.to_dict(),
            "message": f"{entity.capitalize()} updated successfully",
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
    item = Model.query.filter_by(email=login_data["email"],is_deleted=False).first_or_404()
    if not item or not pbkdf2_sha256.verify(login_data["password"], item.password):
        return abort(401, message="Invalid email or password.")
    
    access_token = create_access_token(identity=str(item.id), additional_claims={"role": f"{entity}"}, fresh=True)
    refresh_token = create_refresh_token(identity=str(item.id),additional_claims={"role": f"{entity}"})
    
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
            print("here")
            return { "message":"Wrong password Provided.","status":401},401

        # Update password
        item.password = pbkdf2_sha256.hash(data["new_password"])
        db.session.commit()

        return {"message": "Password updated successfully!"}, 200
    
    except Exception as e:
        db.session.rollback()  # Rollback in case of failure
        return {"error": str(e)}, 500  # Generic error handling



def dailyStatsEntry(restaurant, today, weekday, app):
    print(f"called for {restaurant.id}")
    with app.app_context():
        try:
            # Get restaurant policy & operating hours for today
            policy = restaurant.policy
            operating_hours = restaurant.operating_hours[weekday] if restaurant.operating_hours else None

            if not policy or not operating_hours:
                return 

            # Check if an entry already exists
            existing_entry = DailyStats.query.filter_by(restaurant_id=restaurant.id, date=today).first()
            if existing_entry:
                print(f"entry already exists for {restaurant.id}")
                return 

            # Extract values
            opening_time = max(operating_hours.opening_time, time(0, 0))  # Earliest 00:00
            closing_time = min(operating_hours.closing_time, time(23, 59))  # Latest 23:59
            reservation_duration = policy.reservation_duration  # In minutes
            
            print(f"{opening_time}, {closing_time}, {reservation_duration}")
            # Calculate total slots available in the day
            total_slots = (
                (closing_time.hour * 60 + closing_time.minute  + reservation_duration  - 1) - 
                (opening_time.hour * 60 + opening_time.minute )
            ) // (reservation_duration )

            # Calculate total active tables (tables marked as `is_accessible=True`)
            active_occupancy = (
                db.session.query(db.func.sum(TableInstance.capacity))
                .join(TableType)  # Join TableInstance with TableType
                .filter(
                    TableType.restaurant_id == restaurant.id,  # Filter by restaurant_id from TableType
                    TableType.is_deleted == False,  # Ensure TableType is not deleted
                    TableInstance.is_available == True,  # Ensure TableInstance is accessible
                    TableInstance.is_deleted == False  # Ensure TableInstance is not deleted
                )
                .scalar()  # Get single value instead of a tuple
            ) or 0  # Default to 0 if there are no matching tables


            total_active_occupancy = total_slots * active_occupancy
            
            print(f"{total_slots}, {active_occupancy}, {total_active_occupancy}")

            # Create new entry
            new_entry = DailyStats(
                restaurant_id=restaurant.id,
                date=today,
                total_reservations=0,
                total_cancelled_reservations=0,
                total_revenue=0,
                maximum_occupancy=total_active_occupancy,
                reserved_occupancy=0,
            )

            db.session.add(new_entry)
            db.session.commit()  # Commit only this entry

        except Exception as e:
            db.session.rollback()  # Rollback only if an error occurs for this restaurant
            print(f"Error processing restaurant {restaurant.id}: {e}")



# Haversine formula for calculating distance

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points on the Earth in km."""
    R = 6371  # Earth's radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c



