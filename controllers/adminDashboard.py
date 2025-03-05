
from email import policy
from flask_smorest import Blueprint, abort
from models import *
from datetime import datetime
from sqlalchemy.orm import joinedload
from flask_jwt_extended import (
        get_jwt_identity, 
        jwt_required, 
        get_jwt
    )
from services.helper import generate_time_slots
from datetime import datetime, timedelta

blp = Blueprint("admin_dashboard", __name__, description="Admin Booking Management")


@blp.route("/api/admins/restaurants/bookings_by_slot/<string:date>")
@jwt_required()
def get_bookings(date):
    """This API fetches all active bookings for a restaurant admin on a specific date. It organizes bookings by time slots, showing details"""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

    # Fetch restaurant policy for slot generation
    admin_id = get_jwt_identity()
    restaurant = Restaurant.query.filter(Restaurant.admin_id == admin_id).first()

    
    if not restaurant or not restaurant.policy:
        return {"error": "Restaurant or Restaurant policy not found"}, 404
    restaurant_id = restaurant.id
    policy = restaurant.policy

    # Generate dynamic time slots
    time_slots = generate_time_slots(policy.opening_time, policy.closing_time, policy.reservation_duration)

    # Fetch bookings with proper joins
    bookings = Booking.query.filter_by(restaurant_id=restaurant_id, date=date_obj) \
        .options(
            joinedload(Booking.user),
            joinedload(Booking.tables).joinedload(BookingTable.table).joinedload(TableInstance.table_type)
        ).all()

    # Create a mapping of slots to bookings
    slot_mapping = {slot: [] for slot in time_slots}

    for booking in bookings:
        
        slot = f"{booking.start_time}"

        # Group all table instances under the same table type
        table_types = {}
        for bt in booking.tables:
            table_type = bt.table.table_type
            table_type_key = table_type.id
            if table_type_key not in table_types:
                table_types[table_type_key] = {
                    "table_type": {
                        "table_type_id": table_type.id,
                        "name": table_type.name,
                        "capacity": table_type.capacity,
                        "is_outdoor": table_type.is_outdoor,
                        "is_accessible": table_type.is_accessible,
                        "shape": table_type.shape.name if table_type.shape else None,
                        "price": table_type.price
                    },
                    "tables": []
                }
            table_types[table_type_key]["tables"].append({
                "table_id": bt.table.id,
                "table_number": bt.table.table_number,
                "location": bt.table.location_description
            })

        slot_mapping.setdefault(slot, []).append({
            "booking_id": booking.id,
            "user": {
                "name": booking.user.name,
                "contact": booking.user.phone
            },
            "guest_count": booking.guest_count,
            "status": booking.status,
            "table_groups": list(table_types.values())  # Convert dict to list
        })

    return {"date": date, "slots": slot_mapping}



@blp.route("/api/admins/restaurants/tables/status/<string:date>")
@jwt_required()
def get_all_table_status(date):
    """This API allows an admin to retrieve a detailed availability status of all tables in their restaurant for a specific     date."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")

    # Convert date string to date object
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

    # Fetch restaurant policy for slot generation
    admin_id = get_jwt_identity()
    restaurant = Restaurant.query.filter(Restaurant.admin_id == admin_id).first()

    
    if not restaurant or not restaurant.policy:
        return {"error": "Restaurant or Restaurant policy not found"}, 404
    
    restaurant_id = restaurant.id
    policy = restaurant.policy
    
    time_slots = generate_time_slots(policy.opening_time, policy.closing_time, policy.reservation_duration)

    # Fetch all table types and their tables
    table_types = TableType.query.filter_by(restaurant_id=restaurant_id).options(joinedload(TableType.tables)).all()

    # Fetch bookings for all tables on the given date
    bookings = BookingTable.query.join(Booking).filter(
        Booking.restaurant_id == restaurant_id,
        Booking.date == date_obj,
        Booking.status == "active"
    ).options(joinedload(BookingTable.booking).joinedload(Booking.user)).all()

    # **Step 1: Initialize response structure**
    tables_by_type = {}

    for table_type in table_types:
        table_type_data = {
            "table_type_id": table_type.id,
            "capacity": table_type.capacity,
            "is_outdoor": table_type.is_outdoor,
            "is_accessible": table_type.is_accessible,
            "shape": table_type.shape.name if table_type.shape else None,
            "price": table_type.price
        }
        tables = {}

        # **Step 2: Initialize slot mapping for each table**
        for table in table_type.tables:
            slot_mapping = {slot: {"status": "available"} for slot in time_slots}
            tables[table.table_number] = {"slots": slot_mapping}

        tables_by_type[table_type.id] = {
            "table_type_info": table_type_data,
            "tables": tables
        }

    # **Step 3: Loop through bookings & directly update slot mappings**
    for bt in bookings:
        table_number = bt.table.table_number  # Get table number
        table_type_id = bt.table.table_type.id  # Get table type name
        slot = f"{bt.booking.start_time}"

        # **Directly access the correct table & update its slot**
        if table_number in tables_by_type[table_type_id]["tables"]:
            tables_by_type[table_type_id]["tables"][table_number]["slots"][slot] = {
                "status": "booked",
                "booking_id": bt.booking.id,
                "user": bt.booking.user.name,
                "contact": bt.booking.user.phone,
                "guest_count": bt.booking.guest_count
            }

    return {"date": date, "tables_by_type": tables_by_type}




@blp.route("/api/admins/restaurants/bookings/<string:date>", methods=["GET"])
@jwt_required()
def get_bookings(date):
    
    """This API allows an admin to retrieve the details of all booking in their restaurant for a specific date."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")    
    # Fetch restaurant policy for slot generation
    admin_id = get_jwt_identity()
    restaurant = Restaurant.query.filter(Restaurant.admin_id == admin_id).first()   

    if not restaurant :
        return {"error": "No Restaurant found for this admin"}, 404

    restaurant_id = restaurant.id
    # Fetch bookings ordered by start_time
    bookings = (
        db.session.query(Booking)
        .filter(Booking.restaurant_id == restaurant_id, Booking.date == date)
        .order_by(Booking.start_time.asc())  # Ordering by start_time (earliest first)
        .options(
            joinedload(Booking.user),  # Load user details
            joinedload(Booking.tables).joinedload(BookingTable.table).joinedload(TableInstance.table_type)  # Load tables & table types
        )
        .all()
    )  
    # Transform data
    result = []
    for booking in bookings:
        booking_info = {
            "booking_id": booking.id,
            "start_time": booking.start_time,
            "status": booking.status,
            "user": booking.user.name,
            "contact": booking.user.phone,
            "guest_count": booking.guest_count,
            "table_types": []
        }   
        table_types_map = {}
        for bt in booking.tables:
            table_type = bt.table.table_type
            if table_type.id not in table_types_map:
                table_types_map[table_type.id] = {
                "table_type_id": table_type.id,
                "capacity": table_type.capacity,
                "is_outdoor": table_type.is_outdoor,
                "is_accessible": table_type.is_accessible,
                "shape": table_type.shape.name if table_type.shape else None,
                "price": table_type.price,
                "tables":[]
            }   
            table_types_map[table_type.id]["tables"].append({
                "table_id": bt.table.id,
                "table_number": bt.table.table_number,
                "location_description": bt.table.location_description,
                "is_available": bt.table.is_available
            })  
        booking_info["table_types"] = list(table_types_map.values())  # Convert dict to list
        result.append(booking_info) 
        
    return {"data":result, "message":"All bookings fetched successfully", "status":200}, 200

