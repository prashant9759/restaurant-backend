from flask_smorest import Blueprint, abort
from flask.views import MethodView

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import raiseload, joinedload, subqueryload
from collections import defaultdict

from scheduler import scheduler

from models import *
from schemas import  *
from services.helper import *
from services.helper import generate_time_slots

from db import db
from datetime import datetime, timedelta





blp = Blueprint("Presentation", __name__, description="Routes for our main website page")




def add_table_info(restaurant):
    restaurant_dict = restaurant.to_dict()
    
    # Add the table type and instances
    restaurant_dict["table_types"] = [
        {
            **table_type.to_dict(),
            "tables": [table.to_dict() for table in table_type.tables]  # Add table instances
        }
        for table_type in restaurant.table_types
    ]
    return restaurant_dict


@blp.route("/api/restaurants/all")
class RestaurantList(MethodView):
    def get(self):
        """Fetch all restaurants with required details"""

        restaurants = (
            db.session.query(Restaurant)
            .options(
                subqueryload(Restaurant.table_types).subqueryload(TableType.tables),  # Load table types and instances
            )
            .order_by(Restaurant.city_state_id)  # Order by city_state_id for efficient grouping
            .all()
        )
        city_grouped_restaurants = defaultdict(list)

        # Iterate through the restaurants and group them by city
        for restaurant in restaurants:
            city = restaurant.city_state.city if restaurant.city_state else "Unknown"
            restaurant_dict =  add_table_info(restaurant)
            city_grouped_restaurants[city].append(restaurant_dict)

            # Convert defaultdict to dict before returning
        return {
            "data": dict(city_grouped_restaurants),
            "message": "All restaurants fetched successfully",
            "status": 200
        }, 200



@blp.route("/api/restaurants/city/<int:city_state_id>/categorised_by_cuisines")
class RestaurantList(MethodView):
    def get(self,city_state_id):
        """Fetch all restaurants with required details categorised by cuisines"""

        restaurants = (
            db.session.query(Restaurant)
            .options(
                subqueryload(Restaurant.table_types).subqueryload(TableType.tables),  # Load table types and instances
            )
            .filter(Restaurant.city_state_id == city_state_id)  # Order by city_state_id for efficient grouping
            .all()
        )
        cuisine_grouped_restaurants = defaultdict(list)

        # Iterate through the restaurants and group them by city
        for restaurant in restaurants:
            restaurant_dict =  add_table_info(restaurant)
            
             # Add restaurant under each cuisine category it belongs to
            for cuisine in restaurant.cuisines:
                cuisine_grouped_restaurants[cuisine.name].append(restaurant_dict)
            # Convert defaultdict to dict before returning
        return {
            "data": dict(cuisine_grouped_restaurants),
            "message": "All restaurants fetched successfully",
            "status": 200
        }, 200


@blp.route("/api/restaurants/<int:restaurant_id>/availability/<string:date>")
class AvailableTablesForDate(MethodView):
    def get(self, restaurant_id, date):
        """Fetch count of available tables for each table type on each slot of that date"""
        # Fetch restaurant details
        policy = (
            db.session.query(RestaurantPolicy)
            .join(Restaurant, Restaurant.policy_id == RestaurantPolicy.id)  # Correct join
            .filter(Restaurant.id == restaurant_id)  # Fetch policy for the specific restaurant
            .first()
        )

        if not policy:
            return abort(404, message = "No restaurant or policy found")
        # Generate time slots dynamically based on restaurant timing & reservation duration
        time_slots = generate_time_slots(
            policy.opening_time, 
            policy.closing_time, 
            policy.reservation_duration
        )

        # Fetch only booked tables that match the given date
        booked_data = (
            db.session.query(
                Booking.start_time,
                db.func.count(BookingTable.table_id).label("count"),
                TableInstance.table_type_id
            )
            .join(Booking, BookingTable.booking_id == Booking.id)
            .join(TableInstance, BookingTable.table_id == TableInstance.id)
            .filter(
                Booking.date == date,  # Only for the requested date
                Booking.restaurant_id == restaurant_id,
                Booking.status == "active"
            )
            .group_by(Booking.start_time, TableInstance.table_type_id)
            .all()
        )

        # Organize booked data into a dictionary
        booked_tables_dict = {}

        for start_time, count, table_type_id in booked_data:
            if table_type_id not in booked_tables_dict:
                booked_tables_dict[table_type_id] = {}  # Initialize nested dictionary
            print(f"for type_id {table_type_id} , booked table count is {count}")
            booked_tables_dict[table_type_id][start_time] = count  # Store count for the time slot



        # Fetch all table types in the restaurant along with their details and table count
        table_types = (
            db.session.query(
                TableType.id,
                TableType.name,
                TableType.capacity,
                TableType.description,
                TableType.is_outdoor,
                TableType.is_accessible,
                TableType.shape,
                db.func.count(TableInstance.id).label("count"),
            )
            .outerjoin(TableInstance, TableInstance.table_type_id == TableType.id)  # Use outer join to include table types with zero       tables
            .filter(TableType.restaurant_id == restaurant_id)
            .group_by(TableType.id)
            .all()
        )

        # Convert query results into structured data
        table_types_data = [
            {
                "table_type_id": t.id,
                "name": t.name,
                "capacity": t.capacity,
                "description": t.description,
                "is_outdoor": t.is_outdoor,
                "is_accessible": t.is_accessible,
                "shape": t.shape.name,
                "table_count": t.count,
            }
            for t in table_types
        ]

        # Initialize available data dictionary using table_type_id as the key
        available_data = {
            t["table_type_id"]: {
                "typeInfo": t,  # Store general table type details
                "countInfo": {}  # Will store available count per time slot
            }
            for t in table_types_data
        }

        # Populate available counts for each type_id & slot combination
        for table_type in table_types_data:
            table_type_id = table_type["table_type_id"]
            total_table_count = table_type["table_count"]

            for start_time in time_slots:
                time_slot_key = f"{date}%{start_time}"

                # Get booked tables count (default to 0 if not booked)
                booked_table_count = booked_tables_dict.get(table_type_id, {}).get(start_time, 0)

                # Compute available tables
                available_count = max(0, total_table_count - booked_table_count)

                # Store the available count
                available_data[table_type_id]["countInfo"][time_slot_key] = available_count
        
        return {"data":available_data, "message":"availability data detched successfully", "status":200},200








