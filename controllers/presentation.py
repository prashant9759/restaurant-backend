from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import get_jwt_identity, jwt_required,get_jwt

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import  joinedload, load_only
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





@blp.route("/api/restaurants/categorised_by_city")
class RestaurantList(MethodView):
    def get(self):
        """Fetch all restaurants categorised by city with basic required details(without table-info)"""

        restaurants = (
            db.session.query(Restaurant)
            .filter(Restaurant.is_deleted == False)
            .options(
                load_only(
                    Restaurant.id, Restaurant.name, Restaurant.rating, Restaurant.average_cost_level,
                    Restaurant.street, Restaurant.latitude, Restaurant.longitude, Restaurant.city_state_id,
                    Restaurant.cover_image
                ),
                joinedload(Restaurant.city_state).load_only(
                    CityStateModel.city, CityStateModel.state, CityStateModel.postal_code
                ),
                joinedload(Restaurant.cuisines),  # Fetch related cuisines
                joinedload(Restaurant.food_preferences)  # Fetch related food preferences
            )
            .all()
        )


        restaurants = [
            {
                "restaurant_id": restaurant.id,
                "name": restaurant.name,
                "rating": restaurant.rating,
                "cover_image":restaurant.cover_image,
                "average_cost_level": restaurant.average_cost_level,
                "address": {
                    "city_state_id": restaurant.city_state_id,
                    "street": restaurant.street,
                    "latitude": restaurant.latitude,
                    "longitude": restaurant.longitude,
                    "city": restaurant.city_state.city if restaurant.city_state else None,
                    "state": restaurant.city_state.state if restaurant.city_state else None,
                    "postal_code": restaurant.city_state.postal_code if restaurant.city_state else None
                },
                "cuisines": [cuisine.name for cuisine in restaurant.cuisines] if restaurant.cuisines else [],
                "food_preferences": [pref.name for pref in restaurant.food_preferences] if restaurant.food_preferences else []
            }
            for restaurant in restaurants
        ]
    
        city_grouped_restaurants = defaultdict(list)

        # Iterate through the restaurants and group them by city
        for restaurant in restaurants:
            city = restaurant["address"]["city"] if restaurant["address"]["city"] else "Unknown"
            city_grouped_restaurants[city].append(restaurant)

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
            .filter( Restaurant.city_state_id == city_state_id,Restaurant.is_deleted == False)
            .options(
                load_only(
                    Restaurant.id, Restaurant.name, Restaurant.rating, Restaurant.average_cost_level,
                    Restaurant.street, Restaurant.latitude, Restaurant.longitude, Restaurant.city_state_id,
                    Restaurant.cover_image
                ),
                joinedload(Restaurant.city_state).load_only(
                    CityStateModel.city, CityStateModel.state, CityStateModel.postal_code
                ),
                joinedload(Restaurant.cuisines),  # Fetch related cuisines
                joinedload(Restaurant.food_preferences)  # Fetch related food preferences
            )
            .all()
        )


        restaurants = [
            {
                "restaurant_id": restaurant.id,
                "name": restaurant.name,
                "rating": restaurant.rating,
                "cover_image":restaurant.cover_image,
                "average_cost_level": restaurant.average_cost_level,
                "address": {
                    "city_state_id": restaurant.city_state_id,
                    "street": restaurant.street,
                    "latitude": restaurant.latitude,
                    "longitude": restaurant.longitude,
                    "city": restaurant.city_state.city if restaurant.city_state else None,
                    "state": restaurant.city_state.state if restaurant.city_state else None,
                    "postal_code": restaurant.city_state.postal_code if restaurant.city_state else None
                },
                "cuisines": [cuisine.name for cuisine in restaurant.cuisines] if restaurant.cuisines else [],
                "food_preferences": [pref.name for pref in restaurant.food_preferences] if restaurant.food_preferences else []
            }
            for restaurant in restaurants
        ]
    
        cuisine_grouped_restaurants = defaultdict(list)

        # Iterate through the restaurants and group them by city
        for restaurant in restaurants:
            
             # Add restaurant under each cuisine category it belongs to
            for cuisine in restaurant["cuisines"]:
                cuisine_grouped_restaurants[cuisine].append(restaurant)
            # Convert defaultdict to dict before returning
        return {
            "data": dict(cuisine_grouped_restaurants),
            "message": "All restaurants fetched successfully",
            "status": 200
        }, 200



@blp.route("/api/restaurants/city/<int:city_state_id>/categorised_by_food_preferences")
class RestaurantList(MethodView):
    def get(self,city_state_id):
        """Fetch all restaurants with required details categorised by food_preferences"""

        restaurants = (
            db.session.query(Restaurant)
            .filter( Restaurant.city_state_id == city_state_id,Restaurant.is_deleted == False)
            .options(
                load_only(
                    Restaurant.id, Restaurant.name, Restaurant.rating, Restaurant.average_cost_level,
                    Restaurant.street, Restaurant.latitude, Restaurant.longitude, Restaurant.city_state_id,
                    Restaurant.cover_image
                ),
                joinedload(Restaurant.city_state).load_only(
                    CityStateModel.city, CityStateModel.state, CityStateModel.postal_code
                ),
                joinedload(Restaurant.cuisines),  # Fetch related cuisines
                joinedload(Restaurant.food_preferences)  # Fetch related food preferences
            )
            .all()
        )


        restaurants = [
            {
                "restaurant_id": restaurant.id,
                "name": restaurant.name,
                "rating": restaurant.rating,
                "cover_image":restaurant.cover_image,
                "average_cost_level": restaurant.average_cost_level,
                "address": {
                    "city_state_id": restaurant.city_state_id,
                    "street": restaurant.street,
                    "latitude": restaurant.latitude,
                    "longitude": restaurant.longitude,
                    "city": restaurant.city_state.city if restaurant.city_state else None,
                    "state": restaurant.city_state.state if restaurant.city_state else None,
                    "postal_code": restaurant.city_state.postal_code if restaurant.city_state else None
                },
                "cuisines": [cuisine.name for cuisine in restaurant.cuisines] if restaurant.cuisines else [],
                "food_preferences": [pref.name for pref in restaurant.food_preferences] if restaurant.food_preferences else []
            }
            for restaurant in restaurants
        ]
        
        food_preference_grouped_restaurants = defaultdict(list)

        # Iterate through the restaurants and group them by city
        for restaurant in restaurants:
            
             # Add restaurant under each cuisine category it belongs to
            for food_preference in restaurant["food_preferences"]:
                food_preference_grouped_restaurants[food_preference].append(restaurant)
                
                
        # Convert defaultdict to dict before returning
        return {
            "data": dict(food_preference_grouped_restaurants),
            "message": "All restaurants fetched successfully",
            "status": 200
        }, 200



def is_restaurant_liked_by_user(user_id, restaurant_id):
    """Check if the logged-in user has liked the restaurant."""
    return db.session.query(RestaurantLike).filter_by(user_id=user_id, restaurant_id=restaurant_id).first() is not None




@blp.route("/api/restaurants/<int:restaurant_id>")
@jwt_required(optional=True)  # Allow both logged-in and non-logged-in users
def get_restaurant(restaurant_id):
    user_id = get_jwt_identity()  # Get logged-in user ID (None if not logged in)
    
    if user_id:
        claims = get_jwt()
        if claims.get("role") != "user":
            user_id = None
        
        
    restaurant = (
        db.session.query(Restaurant)
        .options(
            joinedload(Restaurant.policy),
            joinedload(Restaurant.cuisines),
            joinedload(Restaurant.food_preferences),
            joinedload(Restaurant.operating_hours),
            joinedload(Restaurant.reviews),
            joinedload(Restaurant.table_types),
        )
        .filter_by(id=restaurant_id)
        .first_or_404()
    )

    restaurant_data = restaurant.to_dict()
    restaurant_data.pop("admin")
    # If user is logged in, include the 'like' field
    if user_id:
        restaurant_data["like"] = is_restaurant_liked_by_user(user_id, restaurant_id)

    return {"data":restaurant_data, "message":"Restaurant info fetched successfully", "status":200}, 200



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








