
from flask_jwt_extended import get_jwt_identity, jwt_required,get_jwt
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask import current_app

from sqlalchemy.exc import  SQLAlchemyError
from sqlalchemy.orm import joinedload

from scheduler import scheduler

from models import *
from schemas import  *
from services.helper import *

from db import db
from datetime import datetime, timedelta
import pytz

from datetime import timezone


from flask import request
from sqlalchemy.orm import load_only, noload,joinedload
from sqlalchemy import exists



blp = Blueprint("UserRestaurant", __name__, description="Routes for user Restaurant")



# Business Logic Functions

def check_user_role():
    """Check if the JWT contains the 'user' role."""
    claims = get_jwt()
    if claims.get("role") != "user":
        abort(403, message="Access forbidden: User role required.")


    

@blp.route("/api/users/restaurants/<int:restaurant_id>/like-dislike")
class RestaurantLikeDislikeResource(MethodView):

    @jwt_required()
    def post(self,restaurant_id):
        """Like or Dislike a Restaurant"""
        
        data = request.get_json()
        if not data:
            abort(400, message="No data found")
        check_user_role()
        user_id = get_jwt_identity()
        
        # Check if the restaurant exists using `.exists()`
        restaurant_exists = db.session.query(
            exists().where(Restaurant.id == restaurant_id).where(Restaurant.is_deleted == False)
        ).scalar()
        if not restaurant_exists:
            abort(404, message="Restaurant not found")
        
        try:
            feedback = RestaurantLike.query.filter_by(user_id=user_id, restaurant_id=restaurant_id).first()
            if not feedback:
                feedback = RestaurantLike(
                    user_id=user_id, 
                    restaurant_id=restaurant_id,
                    created_at=datetime.utcnow()
                )
                db.session.add(feedback)
                message = "Feedback created successfully"
                status = 201
            else:
                message = "Feedback updated successfully"
                status = 200
                

            if "like" not in data:
                abort(400, message="like not present in data")

            if not isinstance(data["like"], bool):
                abort(400, message="Invalid input")

            # Prevent redundant writes
            if feedback.liked== data["like"]:
                return {"message": "No changes made"}, 200

            feedback.liked = data["like"]

            feedback.updated_at = datetime.utcnow()
            db.session.commit()
            return {"message": message, "status":status}, status

        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="An error occurred while processing feedback")


@blp.route("/api/users/restaurants/<int:restaurant_id>/feedback")
class RestaurantRatingResource(MethodView):

    @jwt_required()
    @blp.arguments(RestaurantReviewSchema)
    def post(self,data, restaurant_id):
        """Give feedback to a Restaurant"""
        check_user_role()
        user_id = get_jwt_identity()
        
        restaurant = db.session.query(Restaurant).options(
            load_only(Restaurant.id, Restaurant.review_count, Restaurant.rating),  # Load only required columns
            noload("*")  # Prevent loading all relationships
        ).filter(
            Restaurant.id == restaurant_id,
            Restaurant.is_deleted == False
        ).first()

        if not restaurant:
            abort(404, message="Restaurant not found")
        
        try:
            # Check if the user has already reviewed this restaurant
            existing_review = RestaurantReview.query.filter_by(user_id=user_id, restaurant_id=restaurant_id).first()

            if existing_review:
                ''' update rating '''
                restaurant.rating = round(
                    (restaurant.rating*restaurant.review_count +data['rating']-existing_review.rating)
                    /(restaurant.review_count),
                    2)
                # Update existing review
                existing_review.rating = round(data["rating"],2)
                existing_review.review = data.get("review", "").strip()
                existing_review.updated_at = datetime.utcnow()
                message = "Review updated successfully!"
                status = 200
                
            else:
                # Create a new review
                new_review = RestaurantReview(
                    user_id=user_id,
                    restaurant_id=restaurant_id,
                    rating=round(data["rating"],2),
                    review=data.get("review", "").strip(),
                )
                db.session.add(new_review)
                message = "Review submitted successfully!"
                status = 201
                
                ''' update rating '''
                restaurant.rating = round(
                    (restaurant.rating * restaurant.review_count + data['rating']) / (1 + restaurant.review_count), 
                    2
                )

                restaurant.review_count +=1
                
            db.session.commit()
            return {"message": message, "status":status}, status

        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="An error occurred while processing review")
            
    
    
            
@blp.route("/api/users/liked-restaurants", methods=["GET"])
@jwt_required()
def get_liked_restaurants():
    check_user_role()
    user_id = get_jwt_identity()  # Get the logged-in user's ID

    liked_restaurants = (
        db.session.query(Restaurant)
        .join(RestaurantLike, Restaurant.id == RestaurantLike.restaurant_id)
        .filter(RestaurantLike.user_id == user_id, RestaurantLike.liked == True, Restaurant.is_deleted == False)
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


    result = [
        {
            "liked":True,
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
        for restaurant in liked_restaurants
    ]
    
    return {"data":result, "message":"All liked restaurants fetched", "status":200}, 200







@blp.route("/api/users/bookings/restaurants/<int:restaurant_id>")
class CreateBooking(MethodView):
    @jwt_required()
    @blp.arguments(BookingRequestSchema)
    def post(self, booking_data, restaurant_id):
        """Create a new booking after validating user, restaurant, and table availability."""
        user_id = get_jwt_identity()
        claims = get_jwt()
        if claims.get("role") != "user":
            abort(403, message="Access forbidden: user role required.")
        
        guest_count = booking_data["guest_count"]
        date = booking_data["date"]
        start_time = booking_data["start_time"]
        table_type_info = booking_data["table_type_info"]

        # Step 1: Validate User
        user = db.session.get(User, user_id)
        if not user:
            return {"message": "User not found."}, 404
        
        # Get current time in IST (India Standard Time)
        local_tz = pytz.timezone("Asia/Kolkata")
        current_time_ist = datetime.now(local_tz)
        
        # Convert `date` and `start_time` to a datetime object in IST
        booking_datetime = datetime.combine(date, datetime.strptime(start_time, "%H:%M").time())
        booking_datetime = local_tz.localize(booking_datetime)
        
        # Ensure that booking time is in the future
        if booking_datetime < current_time_ist:
            return {"message": "Booking time must be in the future."}, 400

        restaurant = (
            db.session.query(Restaurant)
            .filter_by(id=restaurant_id, is_deleted=False)
            .options(joinedload(Restaurant.policy))  # Eagerly load the policy
            .first()
        )

        if not restaurant:
            abort(404, message="Restaurant not found")

        policy = restaurant.policy  # Access the policy directly
        if not restaurant or not policy:
            return {"message": "Restaurant or Restaurant policy not found."}, 404


        # Step 5: Validate Table Types
        table_type_ids = [t["table_type_id"] for t in table_type_info]
        table_types = {t.id: t for t in db.session.execute(
            select(TableType).where(
                TableType.id.in_(table_type_ids),
                TableType.restaurant_id == restaurant_id
            )
        ).scalars().all()}  # Convert to dict for easy lookup

        if len(table_types) != len(table_type_info):
            return {"message": "One or more table types are invalid or unavailable."}, 400

        # Step 6: Fetch already booked tables for the given date & time
        stmt = select(BookingTable.table_id).join(Booking).where(
            Booking.restaurant_id == restaurant_id,
            Booking.date == date,
            Booking.start_time == start_time,
            Booking.status == "active"
            
        )
        already_booked_table_ids = set(db.session.execute(stmt).scalars().all())

        # Step 7: Create Booking Instance
        new_booking = Booking(
            user_id=user_id,
            restaurant_id=restaurant_id,
            guest_count=guest_count,
            date=date,
            start_time=start_time
        )

        # Step 8: Assign Available Tables to Booking
        booked_tables = []
        table_details = {}

        for table_type in table_type_info:
            type_id = table_type["table_type_id"]
            requested_count = table_type.get('count',1)

            # Fetch available tables
            available_tables = db.session.execute(
                select(TableInstance).where(
                    TableInstance.table_type_id == type_id,
                    TableInstance.id.notin_(already_booked_table_ids)
                ).limit(requested_count)
            ).scalars().all()

            if len(available_tables) < requested_count:
                return {"message": f"Not enough available tables for table_type_id {type_id}"}, 400

            # Add to response data
            table_details[type_id] = {
                "table_type_info": table_types[type_id].to_dict(),
                "tables": [table.to_dict() for table in available_tables]
            }

            # Prepare BookingTable instances
            booked_tables.extend([BookingTable(table_id=table.id) for table in available_tables])

        # Associate tables using SQLAlchemy relationship
        new_booking.tables = booked_tables

        # Step 9: Commit Transaction
        try:
            db.session.add(new_booking)
            db.session.commit()
            
            utc_tz = pytz.utc

            start_datetime = datetime.combine(date, datetime.strptime(start_time, "%H:%M").time())
            start_datetime = local_tz.localize(start_datetime)  # Convert to IST

            completion_time = start_datetime + timedelta(minutes=policy.reservation_duration)
            completion_time = completion_time.astimezone(utc_tz)  # Convert to UTC
    

            job_id = f"complete_booking_{new_booking.id}"
            scheduler.add_job(
                id=job_id,
                func=mark_booking_completed,
                args=[current_app._get_current_object(), new_booking.id],
                trigger="date",
                run_date=completion_time,
                replace_existing=True
            )


            return {
                "message": "Booking created successfully",
                "booking_details": {
                    "booking_id": new_booking.id,
                    "user_id": new_booking.user_id,
                    "restaurant_id": new_booking.restaurant_id,
                    "guest_count": new_booking.guest_count,
                    "date": str(new_booking.date),
                    "start_time": str(new_booking.start_time),
                    "assigned_tables": table_details,
                    "status":new_booking.status
                }
            }, 201
        except SQLAlchemyError as e:
            db.session.rollback()
            print(e)
            return {"message": "Error occurred while creating the booking."}, 500



@blp.route("/api/users/bookings/<int:booking_id>/cancel")
class CancelBooking(MethodView):
    @jwt_required()
    def patch(self, booking_id):
        """Cancel a user's booking if it's still within the allowed cancellation period."""
        user_id = get_jwt_identity()
        claims = get_jwt()
        if claims.get("role") != "user":
            abort(403, message="Access forbidden: user role required.")

        # Fetch booking
        booking = db.session.get(Booking, booking_id)
        if not booking:
            return {"message": "Booking not found."}, 404

        # Ensure the booking belongs to the requesting user
        if str(booking.user_id) != user_id:
            return {"message": "Unauthorized to cancel this booking."}, 403

        # Ensure the booking is still active
        if booking.status != "active":
            return {"message": "Booking cannot be canceled as it's not active."}, 400

        restaurant = (
            db.session.query(Restaurant)
            .filter_by(id=booking.restaurant_id, is_deleted=False)
            .options(joinedload(Restaurant.policy))  # Eagerly load the policy
            .first()
        )

        if not restaurant:
            abort(404, message="Restaurant not found")

        policy = restaurant.policy  # Access the policy directly
        if not restaurant or not policy:
            return {"message": "Restaurant or Restaurant policy not found."}, 404

        free_cancellation_window = restaurant.policy.free_cancellation_window  # Time in minutes
        late_cancellation_fee = restaurant.policy.late_cancellation_fee
        # Compute current time and booking start time
        local_tz = pytz.timezone("Asia/Kolkata")  # Assuming IST as the system timezone
        now = datetime.now(local_tz)

        booking_datetime = datetime.combine(
            booking.date, datetime.strptime(booking.start_time, "%H:%M").time()
        )
        booking_datetime = local_tz.localize(booking_datetime)

        # Ensure cancellation is within allowed time
        min_cancellation_time = booking_datetime - timedelta(minutes=free_cancellation_window)
        if now >= min_cancellation_time:
            total_cost = booking.guest_count*late_cancellation_fee
            return {"message": f"Booking is canceled you will be charged {total_cost}"}, 200

        # Update status to 'canceled'
        booking.status = "cancelled"

        # Release booked tables
        # for table in booking.tables:
        #     db.session.delete(table)  # Remove from BookingTable association

        # Commit changes
        try:
            db.session.commit()
            # **Step 1: Remove Scheduled Job**
            job_id = f"complete_booking_{booking.id}"
            if scheduler.get_job(job_id):  
                scheduler.remove_job(job_id)
                print(f"✅ Removed scheduled job: {job_id}")
            else:
                print(f"✅ couldn't find job: {job_id}")
            return {"message": "Booking canceled successfully."}, 200
        except SQLAlchemyError:
            db.session.rollback()
            return {"message": "Error occurred while canceling the booking."}, 500



@blp.route("/api/users/bookings/all", methods=["GET"])
@jwt_required()
def get_user_bookings():
    """Fetch all bookings of a user, categorized into Current, Past, and Cancelled."""

    user_id = get_jwt_identity()
    today = datetime.utcnow().date()

    # Fetch all bookings for the user, ordered by date (latest first)
    bookings = (
        db.session.query(Booking)
        .filter_by(user_id=user_id)
        .options(
            joinedload(Booking.restaurant),  
            joinedload(Booking.tables).joinedload(BookingTable.table).joinedload(TableInstance.table_type)
        )
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )

    categorized_bookings = {"current": [], "past": [], "cancelled": []}

    for booking in bookings:
        table_type_names = list({
            booking_table.table.table_type.name for booking_table in booking.tables
        })  # Get unique table type names

        # Construct booking details
        booking_details = {
            "booking_id": booking.id,
            "restaurant_id": booking.restaurant.id,
            "restaurant_name": booking.restaurant.name,
            "date": booking.date.strftime("%B %d, %Y"),
            "start_time": booking.start_time,
            "guest_count": booking.guest_count,
            "table_types": table_type_names,  
            "status": booking.status,
        }

        # Categorize booking
        if booking.status == "cancelled":
            categorized_bookings["cancelled"].append(booking_details)
        elif booking.date < today:
            categorized_bookings["past"].append(booking_details)
        else:
            categorized_bookings["current"].append(booking_details)

    return {
        "bookings": categorized_bookings,
        "message": "Order details fetched successfully",
        "status": 200
    }, 200



def mark_booking_completed(app,booking_id):
    with app.app_context():
        booking = Booking.query.get(booking_id)
        if booking and booking.status == "active":
            booking.status = "completed"
            db.session.commit()
            print(f"Booking {booking_id} marked as completed.")




