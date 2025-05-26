from email import message
from time import strftime
from flask_smorest import Blueprint, abort
from app import db
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
from sqlalchemy import or_, and_
from sqlalchemy import desc


blp = Blueprint("admin_dashboard", __name__,
                description="Admin Booking Management")


def calculate_slot_count(operating_hours, reservation_duration, start_date, end_date):

    total_slot = 0

    # Loop through each date in the range
    current_date = start_date
    while current_date <= end_date:
        weekday = current_date.weekday()  # 0 (Monday) to 6 (Sunday)

        # Find operating hours for this day
        day_hours = next(
            (oh for oh in operating_hours if oh.day_of_week == weekday), None)

        if day_hours:
            opening_time = datetime.combine(
                current_date, day_hours.opening_time)
            closing_time = datetime.combine(
                current_date, day_hours.closing_time)

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
            slots_count = (closing_minutes -
                           opening_minutes) // reservation_duration
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


def check_admin_role():
    """Check if the JWT contains the 'admin' role."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")


@blp.route("/api/analytics/table-types/<int:restaurant_id>")
@jwt_required()
def get_most_demanded_tables(restaurant_id):
    """Get most demanded table types within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Get table type statistics
    table_stats = db.session.query(
        TableType.id.label('table_type_id'),
        TableType.name,
        func.count(Booking.id).label('count')
    ).join(
        TableInstance, TableInstance.table_type_id == TableType.id
    ).join(
        BookingTable, BookingTable.table_id == TableInstance.id
    ).join(
        Booking, Booking.id == BookingTable.booking_id
    ).filter(
        Booking.date.between(start_date, end_date),
        Booking.restaurant_id == restaurant_id,
        TableType.restaurant_id == restaurant_id,
        TableType.is_deleted == False,
        TableInstance.is_deleted == False
    ).group_by(
        TableType.id,
        TableType.name
    ).order_by(
        desc('count')
    ).paginate(page=page, per_page=per_page)

    return {
        "table_types": [{
            "id": item.table_type_id,
            "name": item.name,
            "count": item.count
        } for item in table_stats.items],
        "total": table_stats.total,
        "pages": table_stats.pages,
        "current_page": table_stats.page
    }


@blp.route("/api/analytics/food-items/<int:restaurant_id>")
@jwt_required()
def get_most_ordered_food(restaurant_id):
    """Get most ordered food items within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Get food item statistics with variants
    food_stats = db.session.query(
        FoodItem.id.label('food_id'),
        FoodItem.name.label('food_name'),
        FoodItemVariant.id.label('variant_id'),
        FoodItemVariant.name.label('variant_name'),
        func.count(OrderItem.id).label('count')
    ).select_from(FoodItem).outerjoin(
        FoodItemVariant, FoodItemVariant.food_item_id == FoodItem.id
    ).join(
        OrderItem,
        or_(
            and_(OrderItem.food_item_id == FoodItem.id,
                 OrderItem.variant_id == None),
            and_(OrderItem.food_item_id == FoodItem.id,
                 OrderItem.variant_id == FoodItemVariant.id)
        )
    ).join(
        ReservationFoodOrder, ReservationFoodOrder.id == OrderItem.order_id
    ).join(
        Booking, Booking.id == ReservationFoodOrder.reservation_id
    ).filter(
        Booking.date.between(start_date, end_date),
        Booking.restaurant_id == restaurant_id,  # Filter by restaurant
        FoodItem.is_deleted == False,
        FoodItem.food_category_id.in_(
            db.session.query(FoodCategory.id)
            .filter(FoodCategory.restaurant_id == restaurant_id)
        ),  # Ensure food items belong to this restaurant
        or_(FoodItemVariant.is_deleted == None,
            FoodItemVariant.is_deleted == False)
    ).group_by(
        FoodItem.id,
        FoodItem.name,
        FoodItemVariant.id,
        FoodItemVariant.name
    ).order_by(
        desc('count')
    ).paginate(page=page, per_page=per_page)

    # Format the results
    items = []
    for stat in food_stats.items:
        item = {
            "food_id": stat.food_id,
            "name": stat.food_name,
            "variant_id": stat.variant_id,
            "variant": stat.variant_name if stat.variant_name else None,
            "count": stat.count
        }
        items.append(item)

    return {
        "food_items": items,
        "total": food_stats.total,
        "pages": food_stats.pages,
        "current_page": food_stats.page
    }


@blp.route("/api/analytics/peak-hours/<int:restaurant_id>")
@jwt_required()
def get_peak_hours(restaurant_id):
    """Get busiest hours within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Get hourly statistics
    hourly_stats = db.session.query(
        func.extract('hour', Booking.start_time).label('hour'),
        func.count(Booking.id).label('count')
    ).filter(
        Booking.date.between(start_date, end_date),
        Booking.restaurant_id == restaurant_id
    ).group_by(
        'hour'
    ).order_by(
        desc('count')
    ).paginate(page=page, per_page=per_page)

    return {
        "busiest_hours": [{
            "hour": int(stat.hour),
            "count": stat.count
        } for stat in hourly_stats.items],
        "total": hourly_stats.total,
        "pages": hourly_stats.pages,
        "current_page": hourly_stats.page
    }


@blp.route("/api/analytics/booking-stats/<int:restaurant_id>")
@jwt_required()
def get_booking_statistics(restaurant_id):
    """Get booking statistics (no-shows, cancellations, completed) within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Get booking statistics
    stats = db.session.query(
        Booking.status,
        func.count(Booking.id).label('count')
    ).filter(
        Booking.date.between(start_date, end_date),
        Booking.restaurant_id == restaurant_id
    ).group_by(
        Booking.status
    ).all()

    return {
        "statistics": {
            "no_shows": next((stat.count for stat in stats if stat.status == 'no_show'), 0),
            "cancelled": next((stat.count for stat in stats if stat.status == 'cancelled'), 0),
            "completed": next((stat.count for stat in stats if stat.status == 'completed'), 0)
        }
    }


@blp.route("/api/analytics/frequent-visitors/<int:restaurant_id>")
@jwt_required()
def get_frequent_visitors(restaurant_id):
    """Get most frequent visitors within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    booking_source = request.args.get(
        'booking_source', 'online', type=str)  # 'online' or 'walk_in'
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Base query filter
    base_filter = [
        Booking.date.between(start_date, end_date),
        Booking.restaurant_id == restaurant_id,
        Booking.status == 'completed'
    ]

    # Add booking source filter if specified
    if booking_source:
        if booking_source not in ['online', 'walkin']:
            abort(400, message="Invalid booking source. Must be 'online' or 'walkin'")
        base_filter.append(Booking.source == booking_source)

    if booking_source == 'online' or not booking_source:
        # Get online booking statistics
        online_stats = db.session.query(
            User.id.label('user_id'),
            (User.first_name + ' ' +
             func.coalesce(User.middle_name + ' ', '') +
             User.last_name).label('name'),
            User.email,
            func.count(Booking.id).label('visit_count')
        ).join(
            Booking, Booking.user_id == User.id
        ).filter(
            *base_filter,
            User.is_deleted == False
        ).group_by(
            User.id,
            User.first_name,
            User.middle_name,
            User.last_name,
            User.email
        ).order_by(
            desc('visit_count')
        ).paginate(page=page, per_page=per_page)

        return {
            "visitors": [{
                "user_id": item.user_id,
                "name": item.name,
                "email": item.email,
                "visit_count": item.visit_count,
                "booking_source": "online"
            } for item in online_stats.items],
            "total": online_stats.total,
            "pages": online_stats.pages,
            "current_page": online_stats.page
        }
    else:  # walk_in
        # Get walk-in booking statistics
        walk_in_stats = db.session.query(
            Booking.customer_name.label('name'),
            Booking.customer_phone.label('phone'),
            func.count(Booking.id).label('visit_count')
        ).filter(
            *base_filter
        ).group_by(
            Booking.customer_name,
            Booking.customer_phone
        ).order_by(
            desc('visit_count')
        ).paginate(page=page, per_page=per_page)

        return {
            "visitors": [{
                "name": item.name,
                "phone": item.phone,
                "visit_count": item.visit_count,
                "booking_source": "walk_in"
            } for item in walk_in_stats.items],
            "total": walk_in_stats.total,
            "pages": walk_in_stats.pages,
            "current_page": walk_in_stats.page
        }


@blp.route("/api/analytics/table-utilization/<int:restaurant_id>")
@jwt_required()
def get_table_utilization(restaurant_id):
    """Get table utilization statistics within a date range for a specific restaurant"""
    # Check admin role
    check_admin_role()

    # Get current user from JWT
    current_user_id = get_jwt_identity()

    # Verify restaurant ownership and check if restaurant is not deleted
    restaurant = Restaurant.query.filter_by(
        id=restaurant_id,
        admin_id=current_user_id,
        is_deleted=False
    ).first()

    if not restaurant:
        abort(404, message="Restaurant not found or you don't have access to it.")

    start_date = request.args.get('start_date', type=str)
    end_date = request.args.get('end_date', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    if not start_date or not end_date:
        abort(400, message="Start date and end date are required")

    start_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Get table utilization statistics
    table_stats = db.session.query(
        TableInstance.id.label('table_id'),
        TableInstance.table_number,
        func.count(Booking.id).label('total_bookings'),
        func.sum(case((Booking.status == 'completed', 1), else_=0)
                 ).label('completed_bookings'),
        func.sum(case((Booking.status == 'no_show', 1), else_=0)
                 ).label('no_show_bookings'),
        func.sum(case((Booking.status == 'cancelled', 1), else_=0)
                 ).label('cancelled_bookings')
    ).join(
        TableType, TableInstance.table_type_id == TableType.id
    ).outerjoin(
        BookingTable, BookingTable.table_id == TableInstance.id
    ).outerjoin(
        Booking, and_(
            Booking.id == BookingTable.booking_id,
            Booking.date.between(start_date, end_date)
        )
    ).filter(
        TableType.restaurant_id == restaurant_id,
        TableType.is_deleted == False,
        TableInstance.is_deleted == False
    ).group_by(
        TableInstance.id,
        TableInstance.table_number
    ).order_by(
        desc('total_bookings')
    ).paginate(page=page, per_page=per_page)

    # Calculate utilization metrics for each table
    tables_data = []
    for stat in table_stats.items:
        # Get total available slots for this table in the date range
        total_slots = TableAvailability.query.filter(
            TableAvailability.table_id == stat.table_id,
            TableAvailability.date.between(start_date, end_date)
        ).with_entities(
            func.sum(func.array_length(TableAvailability.available_slots, 1))
        ).scalar() or 0

        # Calculate utilization metrics
        total_bookings = stat.total_bookings or 0
        completed_bookings = stat.completed_bookings or 0
        no_show_bookings = stat.no_show_bookings or 0
        cancelled_bookings = stat.cancelled_bookings or 0

        utilization_rate = (total_bookings / total_slots *
                            100) if total_slots > 0 else 0
        success_rate = (completed_bookings / total_bookings *
                        100) if total_bookings > 0 else 0

        tables_data.append({
            "table_id": stat.table_id,
            "table_number": stat.table_number,
            "utilization_rate": round(utilization_rate, 2),
            "success_rate": round(success_rate, 2)
        })

    return {
        "tables": tables_data,
        "total": table_stats.total,
        "pages": table_stats.pages,
        "current_page": table_stats.page
    }

















