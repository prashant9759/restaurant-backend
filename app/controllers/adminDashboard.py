from email import message
from time import strftime
from flask_smorest import Blueprint, abort
from app.models import *
from sqlalchemy.orm import joinedload
from flask_jwt_extended import (
        get_jwt_identity, 
        jwt_required, 
        get_jwt
    )
from flask import request
from app.services.helper import generate_time_slots, get_opening_closing_time
from datetime import datetime, timedelta

from sqlalchemy.sql import func
from flask import request
from sqlalchemy.sql.functions import coalesce
from sqlalchemy import or_
from sqlalchemy import desc





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



@blp.route("/api/admins/restaurants/<int:restaurant_id>/bookings/<string:date>", methods=["GET"])
@jwt_required()
def get_bookings(restaurant_id,date):
    """This API fetches all  bookings for a restaurant admin on a specific date"""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

    # Fetch restaurant policy for slot generation
    admin_id = get_jwt_identity()
    restaurant = Restaurant.query.filter(Restaurant.id ==restaurant_id,Restaurant.is_deleted==False).first()

    
    if not restaurant:
        return {"error": "Restaurant not found"}, 404
    
    if str(restaurant.admin_id) != str(admin_id):
        abort(403, message="Access forbidden: You are not the owner of this restaurant.")

    # Fetch bookings with proper joins

    bookings = Booking.query.filter_by(restaurant_id=restaurant_id, date=date_obj) \
        .options(
            joinedload(Booking.user),
            joinedload(Booking.tables).joinedload(BookingTable.table).joinedload(TableInstance.table_type)
        ) \
        .order_by(desc(Booking.start_time)) \
        .all()


    booking_list = []
    
    def construct_username(user):
        parts = [user.first_name]
        if user.middle_name:
            parts.append(user.middle_name)
        if user.last_name:
            parts.append(user.last_name)
        return " ".join(parts)

    for booking in bookings:
        # Determine name and phone based on source
        if booking.source == "online" and booking.user:
            user_info = {
                "id": booking.user.id,
                "username": construct_username(booking.user),
                "phone": booking.user.phone
            }
        else:  # Walk-in
            user_info = {
                "id": None,
                "username": booking.customer_name,
                "phone": booking.customer_phone
            }

        # Format the response
        booking_info = {
            "booking_id": booking.id,
            "date": booking.date.strftime('%Y-%m-%d'),
            "start_time": booking.start_time,
            "guest_count": booking.guest_count,
            "status": booking.status,
            "restaurant_name": booking.restaurant.name if booking.restaurant else None,
            "tables": [
                {
                    "table_id": bt.table.id,
                    "table_number": bt.table.table_number,
                    "capacity": bt.table.capacity,
                    "location_description": bt.table.location_description
                }
                for bt in booking.tables if bt.table
            ]
        }
        
        booking_list.append({"user_info":user_info, "booking_info":booking_info})
    return {"data": booking_list, "message": "Bookings fetched successfully", "status": 200}, 200

    



@blp.route("/api/admins/restaurants/<int:restaurant_id>/tables/status/<string:date>",methods=["GET"])
@jwt_required()
def get_all_table_status(restaurant_id,date):
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
    restaurant = Restaurant.query.filter(Restaurant.id == restaurant_id \
        , Restaurant.is_deleted==False, Restaurant.admin_id==admin_id).first()

    
    if not restaurant or not restaurant.policy or not restaurant.operating_hours:
        return {"error": "Restaurant or Restaurant policy or Restaurant operating hours not found"}, 404
    
    policy = restaurant.policy
    operating_hours = restaurant.operating_hours
    opening_time , closing_time = get_opening_closing_time(date_obj, operating_hours)
    
    if not opening_time or not closing_time:
        return {"data":[], "message":"The restaurant is on holiday on that date", "status":200},200
    
    time_slots = generate_time_slots(opening_time, closing_time, policy.reservation_duration)

    # Step 1: Fetch all valid tables
    tables = TableInstance.query.filter_by(
        is_deleted=False,
        # Optionally, if TableInstance has restaurant_id field, filter by restaurant_id too
    ).all()

    # Step 2: Fetch all bookings for that date
    bookings = Booking.query.filter_by(restaurant_id=restaurant_id, date=date_obj) \
        .filter(Booking.status.in_(["active", "pending"])) \
        .join(BookingTable) \
        .join(TableInstance) \
        .filter(TableInstance.is_deleted == False) \
        .all()

    # Step 3: Create a mapping of (table_id, time_slot) -> 'booked'
    booked_slots = {}

    for booking in bookings:
        for booking_table in booking.tables:
            table_id = booking_table.table_id
            slot_time = booking.start_time  # Assuming booking is tied to 1 slot
            booked_slots.setdefault(table_id, set()).add(slot_time)

    # Step 4: Prepare the final output
    output = []

    for table in tables:
        table_status = {
            "table_id": table.id,
            "table_number": table.table_number,
            "capacity": table.capacity,
            "location_description": table.location_description,
            "slots": []
        }
        for slot in time_slots:
            if table.id in booked_slots and slot in booked_slots[table.id]:
                status = "booked"
            else:
                status = "available"
            table_status["slots"].append({
                "time_slot": slot,
                "status": status
            })

        output.append(table_status)

    return {"data":output, "message":"Status to all the tables fetched succesfully", "status":200}, 200





    
    
    




