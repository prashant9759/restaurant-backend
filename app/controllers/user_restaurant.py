
from flask_jwt_extended import get_jwt_identity, jwt_required,get_jwt
from flask_smorest import Blueprint, abort
from flask.views import MethodView

from sqlalchemy.exc import  SQLAlchemyError
from sqlalchemy.orm import joinedload



from app.models import *
from app.schemas import  *
from app.services.helper import *

from app import db
from datetime import datetime
import pytz



from flask import request
from sqlalchemy.orm import load_only, noload,joinedload
from sqlalchemy import exists
import random
import string

def generate_checkin_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))



blp = Blueprint("UserRestaurant", __name__, description="Routes for user Restaurant")

# Business Logic Functions

def check_user_role():
    """Check if the JWT contains the 'user' role."""
    claims = get_jwt()
    if claims.get("role") != "user":
        abort(403, message="Access forbidden: User role required.")


def verify_table_type_in_restaurant(restaurant_id, table_type_ids):
    existing_table_types = db.session.query(TableType.id).filter(
        TableType.id.in_(table_type_ids),
        TableType.restaurant_id == restaurant_id,
        TableType.is_deleted == False
    ).all()

    found_ids = {row[0] for row in existing_table_types}
    if len(found_ids) != len(set(table_type_ids)):
        abort(404, message="One or more table types not found or have been deleted.")

    

@blp.route("/api/users/like-dislike")
class RestaurantLikeDislikeResource(MethodView):

    @jwt_required()
    def post(self):
        """Like or Dislike a Restaurant"""
        
        data = request.get_json()
        if not data:
            abort(400, message="No data found")
        check_user_role()
        user_id = get_jwt_identity()
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "User not found."}, 404

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
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


@blp.route("/api/users/feedback")
class RestaurantRatingResource(MethodView):

    @jwt_required()
    @blp.arguments(RestaurantReviewSchema)
    def post(self,data):
        """Give feedback to a Restaurant"""
        check_user_role()
        user_id = get_jwt_identity()
        
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "User not found."}, 404

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
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
            


class BookingResources:
    def create_booking(self,booking_data, restaurant_id, source="online", user_id=None):
        try:
            restaurant = db.session.query(Restaurant).filter(
                Restaurant.id == restaurant_id,
                Restaurant.is_deleted == False
            ).first()
            if not restaurant:
                return {"message": "Restaurant not found", "status": 404}, 404
    
            # Validate booking time for online users
            if source == "online" and not self.is_valid_booking_time(
                booking_data["date"], booking_data["start_time"], restaurant.timezone
            ):
                return {"message": "Booking time must be in the future."}, 400
    
            booking_data.setdefault("table_type_info", [])
            verify_table_type_in_restaurant(restaurant_id, booking_data["table_type_info"])
    
            if not restaurant.policy or not restaurant.operating_hours:
                return {"error": "Restaurant policy or hours missing"}, 404
    
            policy = restaurant.policy
            operating_hours = restaurant.operating_hours
            opening_time, closing_time = get_opening_closing_time(booking_data["date"], operating_hours)
    
            if not opening_time or not closing_time:
                return {"message": "Restaurant is closed on that date", "status": 400}, 400
    
            time_slots = generate_time_slots(opening_time, closing_time, policy.reservation_duration)
    
            if booking_data["start_time"] not in time_slots:
                return {"message": "Invalid start time", "status": 400}, 400
    
            booking_start = datetime.combine(
                booking_data["date"],
                datetime.strptime(booking_data["start_time"], "%H:%M").time()
            )
    
            overlapping_bookings = Booking.query.options(joinedload(Booking.tables)).filter(
                Booking.restaurant_id == restaurant_id,
                Booking.date == booking_data["date"],
                Booking.start_time == booking_data["start_time"],
                Booking.status.in_(["active", "pending"])
            ).all()
    
            booked_table_ids = {
                bt.table_id for booking in overlapping_bookings for bt in booking.tables
            }
    
            available_tables = TableInstance.query.join(TableInstance.table_type).filter(
                TableType.restaurant_id == restaurant_id,
                TableInstance.is_available.is_(True),
                ~TableInstance.id.in_(booked_table_ids)
            ).options(joinedload(TableInstance.table_type)).all()
    
            # Table prioritization
            priority_map = {type_id: idx for idx, type_id in enumerate(booking_data["table_type_info"])}
            available_tables.sort(key=lambda t: (priority_map.get(t.table_type_id, float('inf')), t.id))
    
            selected_tables = []
            remaining_guests = booking_data["guest_count"]
    
            for table in available_tables:
                if remaining_guests <= 0:
                    break
                selected_tables.append(table)
                remaining_guests -= table.capacity
    
            if remaining_guests > 0:
                return {"message": "Not enough tables available."}, 400
    
            checkin_code = generate_checkin_code()
    
            new_booking = Booking(
                **{k: v for k, v in booking_data.items() if k not in ["table_type_info"]},
                user_id=user_id,
                restaurant_id=restaurant_id,
                tables=[BookingTable(table=table) for table in selected_tables],
                status="pending",
                source=source,
                checkin_code=checkin_code
            )
    
            db.session.add(new_booking)
            db.session.commit()
    
            return {
                "message": "Booking created successfully.",
                "checkin_code": checkin_code,
                "booking_id": new_booking.id,
                "tables": [
                    {
                        "table_id": table.id,
                        "table_number": table.table_number,
                        "capacity": table.capacity,
                        "table_type_id": table.table_type_id,
                        "table_type_name": table.table_type.name
                    }
                    for table in selected_tables
                ]
            }, 201

        except Exception as e:
            db.session.rollback()
            print("Error while creating booking:", e)
            # traceback.print_exc()  # This prints the full error + stack trace
            abort(500, message="An internal error occurred while creating the booking.")

            
    def is_valid_booking_time(self, date_str, time_str, timezone_str):
        try:
            # Combine date and time into a datetime object
            booking_dt_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

            # Attach the restaurant's timezone
            tz = pytz.timezone(timezone_str)
            booking_dt = tz.localize(booking_dt_naive)

            # Get current time in the same timezone
            now = datetime.now(tz)

            # Compare
            return booking_dt > now

        except Exception as e:
            print(f"[Error in is_valid_booking_time]: {e}")
            return False

    
    def cancel_booking(self,booking_id, restaurant_id, user_id=None, checkin_code=None):
        restaurant = Restaurant.query.filter(
            Restaurant.id == restaurant_id,
            Restaurant.is_deleted == False
        ).first()

        if not restaurant:
            abort(404, message="Restaurant not found")

        try:
            # Fetch the booking
            booking = Booking.query.filter(
                Booking.id == booking_id,
                Booking.restaurant_id == restaurant_id
            ).first()

            if not booking:
                return {"message": "Booking not found."}, 404

            # Authorization logic
            if booking.source == "online":
                if not user_id or str(booking.user_id) != str(user_id):
                    return {"message": "Unauthorized to cancel this booking."}, 403
            elif booking.source == "walkin":
                if not checkin_code or booking.checkin_code != checkin_code:
                    return {"message": "Invalid or missing check-in code for walk-in booking."}, 400
            else:
                return {"message": "Unknown booking source."}, 400

            # Booking must be pending to cancel
            if booking.status != "pending":
                return {"message": "Booking cannot be canceled as it's not in pending status."}, 400

            # Perform cancellation
            booking.status = "cancelled"
            db.session.commit()

            return {"message": "Booking canceled successfully."}, 200

        except Exception as e:
            db.session.rollback()
            print(f"Error while cancelling booking: {e}")
            abort(500, message="An internal error occurred while cancelling the booking.")


booking_resource_instance=BookingResources()


@blp.route("/api/users/online-bookings")
class CreateBooking(MethodView):
    @jwt_required()
    @blp.arguments(BookingRequestSchema)
    def post(self, booking_data):
        """Create a booking for a restaurant."""
        check_user_role()
        user_id = get_jwt_identity()
        
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "User not found."}, 404

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
        return booking_resource_instance.create_booking(
            booking_data=booking_data,
            restaurant_id=restaurant_id,
            source="online",
            user_id=user_id
        )
        
        
@blp.route("/api/users/walkin-bookings")
class CreateBooking(MethodView):
    @jwt_required()
    @blp.arguments(BookingRequestSchema)
    def post(self, booking_data):
        """Create a booking for a restaurant."""
        claims = get_jwt()
        if claims.get("role") != "staff":
            abort(403, message="Access forbidden: Staff role required.")
        user_id = get_jwt_identity()
        
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "Staff not found."}, 404
        
        if not booking_data.get("customer_name") or not booking_data.get("customer_phone"):
            return {"message": "Customer name & phone both are required"}, 400

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
        return booking_resource_instance.create_booking(
            booking_data=booking_data,
            restaurant_id=restaurant_id,
            source="walkin"
        )
        


@blp.route("/api/users/online-bookings/<int:booking_id>/cancel")
class CancelBooking(MethodView):
    @jwt_required()
    def patch(self, booking_id):
        """Cancel a user's booking if it's still within the allowed cancellation period."""
        user_id = get_jwt_identity()
        claims = get_jwt()

        if claims.get("role") != "user":
            abort(403, message="Access forbidden: user role required.")
            
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "User not found."}, 404

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
        return booking_resource_instance.cancel_booking(
            booking_id, 
            restaurant_id, 
            user_id
        )
            
   
@blp.route("/api/users/walkin-bookings/<int:booking_id>/cancel")
class CancelBooking(MethodView):
    @jwt_required()
    def patch(self, booking_id):
        """Cancel a user's booking if it's still within the allowed cancellation period."""
        user_id = get_jwt_identity()
        claims = get_jwt()

        if claims.get("role") != "staff":
            abort(403, message="Access forbidden: staff role required.")
            
        # Fetch the user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()

        if not user:
            return {"message": "Staff not found."}, 404
        
        checkin_code = request.args.get("checkin_code")
        
        if not checkin_code:
            return {"message":"Missing check_in code"}, 400

        # Access the restaurant_id
        restaurant_id = user.restaurant_id
        
        return booking_resource_instance.cancel_booking(
            booking_id, 
            restaurant_id, 
            null,
            checkin_code
        )
                 
    

@blp.route("/api/users/online-bookings/all", methods=["GET"])
@jwt_required()
def get_user_bookings():
    """Fetch all bookings of a user, categorized into Current, Past, and Cancelled."""

    user_id = get_jwt_identity()
    check_user_role()
    
    # Fetch the user
    user = User.query.filter_by(id=user_id, is_deleted=False).first()
    if not user:
        return {"message": "User not found."}, 404
    # Access the restaurant_id
    restaurant_id = user.restaurant_id
    
    restaurant=Restaurant.query.filter(
        Restaurant.id==restaurant_id,
        Restaurant.is_deleted==False
    ).first()
        
    if not restaurant:
        abort(404,message="Restaurant not found")
    
    today = datetime.utcnow().date()

    # Fetch all bookings for the user, ordered by date (latest first)
    bookings = (
        db.session.query(Booking)
        .filter_by(user_id=user_id,restaurant_id=restaurant_id)
        .options(
            joinedload(Booking.restaurant),  
        )
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )

    categorized_bookings = {"current": [], "past": [], "cancelled": []}

    for booking in bookings:
        # Construct booking details
        booking_details = {
            "date": booking.date.strftime("%B %d, %Y"),
            "start_time": booking.start_time,
            "guest_count": booking.guest_count,
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
        "message": "Booking details details fetched successfully",
        "status": 200
    }, 200


@blp.route("/api/users/bookings/checkin")
class BookingCheckIn(MethodView):
    @jwt_required()
    def post(self):
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Access forbidden: staff role required.")
                
            # Fetch the user
            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404
            
            code = request.args.get("checkin_code")
            if not code:
                abort(400, message="Missing check-in code.")

            booking = Booking.query.options(
                joinedload(Booking.tables).joinedload(BookingTable.table)
            ).filter_by(checkin_code=code).first()

            if not booking:
                abort(404, message="Invalid check-in code.")
            if booking.status != "pending":
                return {"message": "Booking already checked in or canceled."}, 400

            booking.status = "active"
            db.session.commit()

            booking_data = {
                "id": booking.id,
                "restaurant_id": booking.restaurant_id,
                "date": booking.date.isoformat(),
                "start_time": booking.start_time,
                "status": booking.status,
                "checkin_code": booking.checkin_code,
                "tables": [
                    {
                        "id": bt.table.id,
                        "table_number": bt.table.table_number,
                        "capacity": bt.table.capacity
                    }
                    for bt in booking.tables
                ]
            }
            
            # Conditionally include user info
            if booking.user_id:
                booking_data["user_id"] = booking.user_id
            else:
                booking_data["customer_name"] = booking.customer_name
                booking_data["customer_phone"] = booking.customer_phone


            return {"message": "Check-in successful.", "booking": booking_data}, 200

        except Exception as e:
            db.session.rollback()
            print(f"Error during check-in: {e}")
            abort(500, message="An internal error occurred during check-in.")

