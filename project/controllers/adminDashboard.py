from email import message
from time import strftime
from flask_smorest import Blueprint, abort
from project.models import *
from sqlalchemy.orm import joinedload
from flask_jwt_extended import (
        get_jwt_identity, 
        jwt_required, 
        get_jwt
    )
from flask import request
from project.services.helper import generate_time_slots
from datetime import datetime, timedelta, date

from sqlalchemy.sql import func
from flask import request
from sqlalchemy.sql.functions import coalesce



blp = Blueprint("admin_dashboard", __name__, description="Admin Booking Management")

def calculate_slot_count(operating_hours,reservation_duration, start_date, end_date):

    total_slot = 0

    # Loop through each date in the range
    current_date = start_date
    while current_date <= end_date:
        weekday = current_date.weekday()  # 0 (Monday) to 6 (Sunday)

        # Find operating hours for this day
        day_hours = next((oh for oh in operating_hours if oh.day_of_week == weekday), None)

        if day_hours:
            opening_time = datetime.combine(current_date, day_hours.opening_time)
            closing_time = datetime.combine(current_date, day_hours.closing_time)

            # Count available slots
            total_slot += (closing_time-opening_time)//reservation_duration

        current_date += timedelta(days=1)
    
    return total_slot



def get_slots_per_working_day(restaurant):

    reservation_duration = restaurant.policy.reservation_duration  # Duration in minutes
    slots_per_day = {}

    for entry in restaurant.operating_hours:
        opening_time = entry.opening_time  # time object
        closing_time = entry.closing_time  # time object

        # Convert times to minutes since midnight
        opening_minutes = opening_time.hour * 60 + opening_time.minute
        closing_minutes = closing_time.hour * 60 + closing_time.minute

        # Calculate the number of slots
        if closing_minutes > opening_minutes:  # Ensure valid operating hours
            slots_count = (closing_minutes - opening_minutes) // reservation_duration
            slots_per_day[entry.day_of_week] = slots_count

    return slots_per_day



def get_total_slots_in_range(slots_per_day, start_date, end_date):
    """
    Calculate total available slots in a restaurant for a given date range.
    
    Args:
    - slots_per_day.
    - start_date: Start date (datetime.date).
    - end_date: End date (datetime.date).
    
    Returns:
    - Total slot count in the range.
    """


    total_slots = 0
    current_date = start_date

    while current_date <= end_date:
        weekday = current_date.weekday()  # Monday = 0, Sunday = 6
        if weekday in slots_per_day:
            total_slots += slots_per_day[weekday]
        current_date += timedelta(days=1)

    return total_slots



def get_restaurant_stats(restaurant_id, start_date, end_date, Model):
    stats = db.session.query(
        func.sum(Model.total_reservations).label('total_reservations'),
        func.sum(Model.total_cancelled_reservations).label('total_cancelled_reservations'),
        func.sum(Model.reserved_occupancy).label('total_reserved_occupancy'),
        func.sum(Model.maximum_occupancy).label('total_maximum_occupancy'),
        func.sum(Model.total_revenue).label('total_revenue'),
        func.sum(Model.total_refund).label('total_refund')
    ).filter(
        Model.restaurant_id == restaurant_id,
        Model.date.between(start_date, end_date)
    ).first()

    return {
        "total_reservations": stats.total_reservations or 0,
        "total_cancelled_reservations": stats.total_cancelled_reservations or 0,
        "total_reserved_occupancy": stats.total_reserved_occupancy or 0,
        "total_maximum_occupancy": stats.total_maximum_occupancy or 0,
        "total_revenue": stats.total_revenue or 0.0,
        "total_refund": stats.total_refund or 0.0
    }



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



@blp.route("/api/admins/restaurants/<int:restaurant_id>/dashboard", methods = ["POST"])
@jwt_required()
def get_dashboard_data(restaurant_id):
    
    try:
        # Parse JSON request body
        date_range = request.json
        
        # Validate required fields
        if "start_date" not in date_range or "end_date" not in date_range:
            return {"error": "start_date and end_date are required"}, 400
        
        # Convert strings to date objects
        start_date = datetime.strptime(date_range["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(date_range["end_date"], "%Y-%m-%d").date()

        # Ensure start_date is before or equal to end_date
        if start_date > end_date:
            return {"error": "start_date cannot be after end_date"}, 400

        print(f"start_date: {str(start_date)}, end_date: {str(end_date)}")
    
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400
    
    
    today_date = datetime.today().date()
    yesterday_date = (datetime.today() - timedelta(days=1)).date()
    tomorrow_date = (datetime.today() + timedelta(days=1)).date()
    today_weekday = datetime.utcnow().weekday()  # 0 = Monday, 6 = Sunday
    
    current_time = datetime.now().replace(second=0, microsecond=0)

    
    restaurant = db.session.query(Restaurant).options(
        joinedload(Restaurant.policy),
        joinedload(Restaurant.operating_hours)
    ).join(
        RestaurantOperatingHours
    ).filter(
        Restaurant.is_deleted == False,
        Restaurant.id == restaurant_id
    ).first()
    
    if not restaurant:
        abort(404, message = "No restaurant found with this id")
    if not restaurant.policy:
        abort(400, message = "restaurant has no policy")
    if not restaurant.operating_hours:
        abort(400, message = "Restaurant working days aren't set yet")
    
    res = get_restaurant_stats(restaurant_id, today_date,end_date,DailyStats)
    
    
    if(start_date<=yesterday_date):
        left_res = get_restaurant_stats(restaurant_id, start_date,yesterday_date,HourlyStats)
        res["total_reservations"] += left_res["total_reservations"]
        res["total_cancelled_reservations"] += left_res["total_cancelled_reservations"]
        res["total_reserved_occupancy"] += left_res["total_reserved_occupancy"]
        res["total_maximum_occupancy"] += left_res["total_maximum_occupancy"]
        res["total_revenue"] += left_res["total_revenue"]
        res["total_refund"] += left_res["total_refund"]
        
    extra_slot_count = 0
    
    # Get today's operating hours
    today_hours = next((oh for oh in restaurant.operating_hours if oh.day_of_week == today_weekday), None)

    if today_hours:
        opening_time = today_hours.opening_time
        closing_time = today_hours.closing_time

        reservation_duration = timedelta(minutes=restaurant.policy.reservation_duration)

        # Generate all possible time slots
        current_slot = datetime.combine(datetime.utcnow().date(), opening_time)
        closing_datetime = datetime.combine(datetime.utcnow().date(), closing_time)
        last_slot = closing_datetime

        while current_slot + reservation_duration <= closing_datetime:
            if current_slot >= current_time:
                last_slot = current_slot
                break
            current_slot += reservation_duration
        
        extra_slot_count += (closing_datetime-last_slot)//reservation_duration
    
    if(tomorrow_date<=end_date):
        extra_slot_count += calculate_slot_count(restaurant.operating_hours,
            reservation_duration,tomorrow_date,end_date)
    
    total_capacity = 0
    if extra_slot_count:
        total_capacity = db.session.query(
            func.sum(TableInstance.capacity)
        ).join(TableType).filter(
            TableType.restaurant_id == restaurant_id,
            TableInstance.is_deleted == False,
            TableInstance.is_available == True
        ).scalar()

    if not total_capacity:
        total_capacity = 0
    total_extra_occupancy = extra_slot_count*total_capacity
    res["total_maximum_occupancy"] += total_extra_occupancy
    return res
    
    res["total_maximum_occupancy"] += total_extra_occupancy
    
    final_res = {}
    final_res["total_reservations"] = res["total_cancelled_reservations"]
    final_res["revenue"] = res["total_revenue"]
    final_res["occupancy_rate"] =coalesce(round((res["total_reserved_occupancy"]/
        res["total_maximum_occupancy"])*100,2),0)
    
    


    
    
    




