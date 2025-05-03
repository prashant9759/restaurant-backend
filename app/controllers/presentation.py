from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import get_jwt_identity, jwt_required,get_jwt

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import  joinedload, load_only
from collections import defaultdict


from app.models import *
from app.schemas import  *
from app.services.helper import *
from app.services.helper import generate_time_slots

from app import db
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

        # Convert date string to date object
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

        # Fetch restaurant policy for slot generation
        restaurant = Restaurant.query.filter(Restaurant.id == restaurant_id \
            , Restaurant.is_deleted==False).first()


        if not restaurant or not restaurant.policy or not restaurant.operating_hours:
            return {"error": "Restaurant or Restaurant policy or Restaurant operating hours not found"}, 404

        policy = restaurant.policy
        operating_hours = restaurant.operating_hours
        opening_time , closing_time = get_opening_closing_time(date_obj, operating_hours)

        if not opening_time or not closing_time:
            return {"data":[], "message":"The restaurant is on holiday on that date", "status":200},200

        time_slots = generate_time_slots(opening_time, closing_time, policy.reservation_duration)

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
                TableType.minimum_capacity,
                TableType.maximum_capacity,
                TableType.description,
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
                "min_capacity": t.minimum_capacity,
                "max_capacity":t.maximum_capacity,
                "description": t.description,
                "shape": t.shape,
                "total_table_count": t.count,
            }
            for t in table_types
        ]
        

        # Initialize available data dictionary using table_type_id as the key
        available_data =[]

        # Populate available counts for each type_id & slot combination
        for table_type in table_types_data:
            item ={}
            item["table_type_info"]=table_type
            item["countInfo"]=[]
            table_type_id = table_type["table_type_id"]
            total_table_count = table_type["total_table_count"]

            for start_time in time_slots:
                time_slot_key = f"{start_time}"

                # Get booked tables count (default to 0 if not booked)
                booked_table_count = booked_tables_dict.get(table_type_id, {}).get(start_time, 0)

                # Compute available tables
                available_count = max(0, total_table_count - booked_table_count)

                # Store the available count
                item["countInfo"].append({"slot":time_slot_key,"available_count": available_count})
            available_data.append(item)
        
        return {"data":available_data, "message":"availability data fetched successfully", "status":200},200








