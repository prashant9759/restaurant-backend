import stat
from flask_smorest import Blueprint, abort
from models import *
from sqlalchemy.orm import joinedload
from flask_jwt_extended import (
        get_jwt_identity, 
        jwt_required, 
        get_jwt
    )
from services.helper import generate_time_slots
from datetime import datetime, timedelta, date

from sqlalchemy.sql import func
from flask import request
from collections import defaultdict



blp = Blueprint("admin_dashboard", __name__, description="Admin Booking Management")



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






@blp.route("/api/admins/restaurants/<int:restaurant_id>/dash_board", methods=["GET"])
@jwt_required()
def get_dashboard_data(restaurant_id):
    
    """Get total_reservations, occupancy_rate, revenue & popular time for today, this_week , this_month along with upcoming orders"""
    
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")

    # Fetch restaurant policy for slot generation
    admin_id = get_jwt_identity()
    
    # Fetch restaurant with policy and operating hours in a single query
    restaurant = (
        Restaurant.query
        .options(
            joinedload(Restaurant.operating_hours),  # Load operating hours
            joinedload(Restaurant.policy)  # Load policy
        )
        .filter_by(id=restaurant_id, is_deleted=False, admin_id=admin_id)
        .first_or_404(description="Restaurant not found or deleted.")
    )
        
    # Ensure the restaurant has a policy
    if not restaurant.policy:
        raise ValueError("Restaurant policy not found.")
    
    slot_count = get_slots_per_working_day(restaurant)
    total_slot = {}
    today = date.today()
    total_slot["today"] = get_total_slots_in_range(slot_count,today,today)
    # print(f'slot count for toay {total_slot["today"]}')
    now = datetime.now()
    
    start_of_week = today - timedelta(days=today.weekday())  # Monday of this week
    end_of_week = start_of_week + timedelta(days=6)  # Sunday of this week
    total_slot["this_week"] = get_total_slots_in_range(slot_count,start_of_week,end_of_week)
    
    start_of_month = today.replace(day=1)  # 1st of this month
    last_day_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)  # Last day of this month
    total_slot["this_month"] = get_total_slots_in_range(slot_count,start_of_month,last_day_of_month)
    
    
    

    # Fetch reservations with full user name
    reservations = db.session.query(
        Booking.id, 
        Booking.date, 
        Booking.start_time, 
        Booking.guest_count, 
        Booking.status,
        func.sum(TableType.reservation_fees).label("total_amount"),
        func.count(BookingTable.id).label("occupied_tables"),
        func.group_concat(TableInstance.id).label("table_ids"),  # ✅ Fix here
        func.group_concat(TableType.name).label("table_names"),  # ✅ Fix here
        func.concat(
            User.first_name, 
            " ",  
            func.coalesce(User.middle_name, ""),  # ✅ Ensure middle name is handled properly
            " ",  
            User.last_name
        ).label("user_name")  # ✅ Full Name (First Middle Last)
    ).join(User, Booking.user_id == User.id)\
     .join(BookingTable, Booking.id == BookingTable.booking_id)\
     .join(TableInstance, BookingTable.table_id == TableInstance.id)\
     .join(TableType, TableInstance.table_type_id == TableType.id)\
     .filter(
        Booking.restaurant_id == restaurant_id,
        Booking.date >= start_of_month,
        Booking.date <= max(last_day_of_month,end_of_week)
    )\
     .group_by(Booking.id, User.first_name, User.middle_name, User.last_name)\
     .order_by(Booking.date.asc(), Booking.start_time.asc())\
     .all()


    # ✅ Initialize counters for each category
    categories = {
        "today": {"reservations": 0, "revenue": 0, "occupancy_rate": 0, "popular_time": {}, "occupied_tables": 0},
        "this_week": {"reservations": 0, "revenue": 0, "occupancy_rate": 0, "popular_time": {}, "occupied_tables": 0},
        "this_month": {"reservations": 0, "revenue": 0, "occupancy_rate": 0, "popular_time": {}, "occupied_tables": 0}
    }
    total_reservations = 0
    
    total_tables = db.session.query(func.count(TableInstance.id))\
    .join(TableType, TableInstance.table_type_id == TableType.id)\
    .filter(TableType.restaurant_id == restaurant_id)\
    .scalar() or 1
    print(f"total_tables {total_tables}")
    
    upcoming_reservations = []

    # ✅ Process reservations
    for res in reservations:
        total_reservations += 1
        res_datetime = datetime.combine(res.date, datetime.strptime(res.start_time, "%H:%M").time())


        if res.status =="active" or res.status =="completed":
            # ✅ Categorizing data into Today, This Week, and This Month
            if res.date == today:
                categories["today"]["reservations"] += 1
                categories["today"]["revenue"] += res.total_amount or 0
                categories["today"]["occupied_tables"] += res.occupied_tables
                if res.start_time in categories["today"]["popular_time"]:
                    categories["today"]["popular_time"][res.start_time] += 1
                else:
                    categories["today"]["popular_time"][res.start_time] = 1

            if start_of_week <= res.date <= end_of_week:
                categories["this_week"]["reservations"] += 1
                categories["this_week"]["revenue"] += res.total_amount or 0
                categories["this_week"]["occupied_tables"] += res.occupied_tables
                if res.start_time in categories["this_week"]["popular_time"]:
                    categories["this_week"]["popular_time"][res.start_time] += 1
                else:
                    categories["this_week"]["popular_time"][res.start_time] = 1

            if start_of_month <= res.date <= last_day_of_month:
                categories["this_month"]["reservations"] += 1
                categories["this_month"]["revenue"] += res.total_amount or 0
                categories["this_month"]["occupied_tables"] += res.occupied_tables
                if res.start_time in categories["this_month"]["popular_time"]:
                    categories["this_month"]["popular_time"][res.start_time] += 1
                else:
                    categories["this_month"]["popular_time"][res.start_time] = 1


        # ✅ Only add future reservations to upcoming reservations
        if res_datetime >= now:
            upcoming_reservations.append({
                "user_name": res.user_name,  # ✅ Include User Name
                "date": res.date.strftime("%Y-%m-%d"),
                "time": datetime.strptime(res.start_time, "%H:%M").strftime("%H:%M")
,
                "guests": res.guest_count,
                "status": res.status,
                "tables": [{"id": table_id, "name": table_name} for table_id, table_name in zip(res.table_ids, res.table_names)]
            })

    # ✅ Calculate occupancy rate and popular time for each category
    for key in categories:
        if total_tables > 0:
            print(f'key is {key}, no of occupied tables is  {categories[key]["occupied_tables"]}, total_slot_count is {total_slot[key]}, total_tables is {total_tables}')
            categories[key]["occupancy_rate"] = round((categories[key]["occupied_tables"] / (total_slot[key]*total_tables)) * 100, 2)

        # Determine the most popular time slot
        if categories[key]["popular_time"]:
            categories[key]["popular_time"] = max(categories[key]["popular_time"], key=categories[key]["popular_time"].get)
        else:
            categories[key]["popular_time"] = "N/A"

    # ✅ Sort upcoming reservations by date & time (ascending)
    upcoming_reservations.sort(key=lambda r: (r["date"], r["time"]))

    # ✅ Final response
    data = {
        "today": {
            "total_reservations": categories["today"]["reservations"],
            "occupancy_rate": f"{categories['today']['occupancy_rate']}%",
            "revenue": categories["today"]["revenue"],
            "popular_time": categories["today"]["popular_time"]
        },
        "this_week": {
            "total_reservations": categories["this_week"]["reservations"],
            "occupancy_rate": f"{categories['this_week']['occupancy_rate']}%",
            "revenue": categories["this_week"]["revenue"],
            "popular_time": categories["this_week"]["popular_time"]
        },
        "this_month": {
            "total_reservations": categories["this_month"]["reservations"],
            "occupancy_rate": f"{categories['this_month']['occupancy_rate']}%",
            "revenue": categories["this_month"]["revenue"],
            "popular_time": categories["this_month"]["popular_time"]
        },
        "upcoming_reservations": upcoming_reservations 
    }

    return {"data":data},200


from collections import defaultdict
from sqlalchemy.sql import func, case
from sqlalchemy import Integer

def get_table_utilization(start_date, end_date, restaurant_id):
    utilization = (
        db.session.query(
            TableType.name,
            func.coalesce(func.count(BookingTable.id), 0).label("occupied_tables"),  # Ensure no NULL values
            func.count(TableInstance.id).label("total_tables")
        )
        .join(TableInstance, TableType.id == TableInstance.table_type_id)
        .outerjoin(BookingTable, TableInstance.id == BookingTable.table_id)
        .outerjoin(Booking, BookingTable.booking_id == Booking.id)
        .filter(TableType.restaurant_id == restaurant_id)
        .group_by(TableType.name)
        .all()
    )

    return {
        record.name: round((record.occupied_tables / record.total_tables) * 100, 2) if record.total_tables else 0
        for record in utilization
    }


def get_time_based_occupancy(start_date, end_date, restaurant_id):
    # Query actual data
    time_occupancy = (
        db.session.query(
            func.hour(Booking.start_time).label("hour"),
            func.dayofweek(Booking.date).label("day_of_week"),
            func.count(BookingTable.id).label("occupied_tables"),
        )
        .join(BookingTable, Booking.id == BookingTable.booking_id)
        .filter(
            Booking.restaurant_id == restaurant_id,
            Booking.date.between(start_date, end_date),
            Booking.status.in_(["active", "completed"]),
        )
        .group_by(func.hour(Booking.start_time), func.dayofweek(Booking.date))
        .all()
    )

    # Create a default structure to ensure all hours (0-23) and all days (1-7) are included
    occupancy_data = {day: {hour: 0 for hour in range(24)} for day in range(1, 8)}

    # Populate actual data
    for record in time_occupancy:
        occupancy_data[record.day_of_week][record.hour] = record.occupied_tables

    # Flatten the data and sort
    flattened_data = [
        {"day": day, "hour": hour, "occupancy": occupancy}
        for day, hours in occupancy_data.items()
        for hour, occupancy in hours.items()
    ]
    
    # Sort by occupancy to get peak and slowest times
    sorted_times = sorted(flattened_data, key=lambda x: x["occupancy"], reverse=True)

    peak_hours = sorted_times[:3]  # Top 3 busiest times
    slowest_times = sorted_times[-3:]  # Bottom 3 least busy times

    return {
        "peak_hours": peak_hours,
        "slowest_times": slowest_times
    }



@blp.route("/api/admins/restaurants/<int:restaurant_id>/dashboard/analytics_dashboard/restaurant_performance", methods=["POST"])
@jwt_required()
def get_restaurant_performance_data(restaurant_id):
    """This API allows an admin to retrieve key booking metrics for their restaurant, including total reservations, average occupancy, average party size, revenue per booking, and upcoming reservations, categorized by today, this week, and this month."""

    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")

    admin_id = get_jwt_identity()
    restaurant = (
        Restaurant.query
        .options(joinedload(Restaurant.operating_hours), joinedload(Restaurant.policy))
        .filter_by(id=restaurant_id, is_deleted=False, admin_id=admin_id)
        .first_or_404(description="Restaurant not found or deleted.")
    )

    if not restaurant.policy:
        raise ValueError("Restaurant policy not found.")

    # Extract date ranges from request
    data = request.get_json()
    current_start_date = data.get("current_start_date")
    current_end_date = data.get("current_end_date")
    previous_start_date = data.get("previous_start_date")
    previous_end_date = data.get("previous_end_date")

    if not all([current_start_date, current_end_date, previous_start_date, previous_end_date]):
        abort(400, message="Please provide all required date ranges.")

    try:
        current_start_date = datetime.strptime(current_start_date, "%Y-%m-%d").date()
        current_end_date = datetime.strptime(current_end_date, "%Y-%m-%d").date()
        previous_start_date = datetime.strptime(previous_start_date, "%Y-%m-%d").date()
        previous_end_date = datetime.strptime(previous_end_date, "%Y-%m-%d").date()
    except ValueError:
        abort(400, description="Invalid date format. Please use YYYY-MM-DD.")

    if current_start_date > current_end_date or previous_start_date > previous_end_date:
        abort(400, message="Start date cannot be after end date.")
        
    total_tables = db.session.query(func.count(TableInstance.id)) \
        .join(TableType, TableInstance.table_type_id == TableType.id) \
        .filter(TableType.restaurant_id == restaurant_id) \
        .scalar() or 1
        

    def fetch_metrics(start_date, end_date, total_slot):
        reservations = db.session.query(
            func.count(Booking.id).label("total_reservations"),
            func.sum(Booking.guest_count).label("total_guests"),
            func.sum(TableType.reservation_fees).label("total_revenue"),
            func.count(BookingTable.id).label("total_occupied_tables")
        ).join(BookingTable, Booking.id == BookingTable.booking_id) \
         .join(TableInstance, BookingTable.table_id == TableInstance.id) \
         .join(TableType, TableInstance.table_type_id == TableType.id) \
         .filter(
            Booking.restaurant_id == restaurant_id,
            Booking.date.between(start_date, end_date),
            Booking.status.in_(["active", "completed"])  # Correct filtering
        ).first()

        total_reservations = reservations.total_reservations or 0
        total_guests = reservations.total_guests or 0
        total_revenue = reservations.total_revenue or 0
        total_occupied_tables = reservations.total_occupied_tables or 0

        avg_occupancy = round((total_occupied_tables / (total_tables*total_slot)) * 100, 2) if total_tables > 0 else 0
        avg_party_size = round(total_guests / total_reservations, 2) if total_reservations > 0 else 0
        revenue_per_booking = round(total_revenue / total_reservations, 2) if total_reservations > 0 else 0

        return {
            "total_reservations": total_reservations,
            "average_occupancy": avg_occupancy,
            "average_party_size": avg_party_size,
            "revenue_per_booking": revenue_per_booking
        }

    
    slot_count = get_slots_per_working_day(restaurant)
    
    # Fetch data for current and previous periods
    total_current_slot = get_total_slots_in_range(slot_count,current_start_date,current_end_date)
    total_previous_slot = get_total_slots_in_range(slot_count,previous_start_date,previous_end_date)
    
    current_data = fetch_metrics(current_start_date, current_end_date,total_current_slot)
    previous_data = fetch_metrics(previous_start_date, previous_end_date,total_previous_slot)
    print(current_data)

    def calculate_percentage_change(current, previous):
        if previous == 0:
            return "N/A" if current == 0 else "∞%"
        return f"{round(((current - previous) / previous) * 100, 2)}%"

    # Compute trends
    data = {
        "total_reservations": {
            "value": current_data["total_reservations"],
            "trend": calculate_percentage_change(current_data["total_reservations"], previous_data["total_reservations"])
        },
        "average_occupancy": {
            "value": f"{current_data['average_occupancy']}%",
            "trend": calculate_percentage_change(current_data["average_occupancy"], previous_data["average_occupancy"])
        },
        "average_party_size": {
            "value": current_data["average_party_size"],
            "trend": calculate_percentage_change(current_data["average_party_size"], previous_data["average_party_size"])
        },
        "revenue_per_booking": {
            "value": f"${current_data['revenue_per_booking']}",
            "trend": calculate_percentage_change(current_data["revenue_per_booking"], previous_data["revenue_per_booking"])
        }
    }
    print(f"get_time_based_occupancy -> {get_time_based_occupancy(current_start_date,current_end_date,restaurant_id)}")
    print(f"get_table_utilization {get_table_utilization(current_end_date, current_end_date, restaurant_id)}")
    return {"data": data}, 200
