
from flask_jwt_extended import get_jwt_identity, jwt_required,get_jwt
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask import current_app

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
import pytz

from datetime import timezone


blp = Blueprint("UserBooking", __name__, description="Routes for user booking")







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

        # Step 2: Validate Restaurant
        restaurant = db.session.get(Restaurant, restaurant_id)
        if not restaurant:
            return {"message": "Restaurant not found."}, 404

        # Step 3: Fetch restaurant policy for table availability checks
        policy = restaurant.policy
        if not policy:
            return {"message": "Restaurant policy not found."}, 404

        # Step 4: Generate valid time slots
        time_slots = generate_time_slots(
            policy.opening_time, policy.closing_time, policy.reservation_duration
        )
        if start_time not in time_slots:
            return {"message": "Invalid booking time."}, 400

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
            requested_count = table_type["count"]

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
            
            # Compute the exact completion time
            local_tz = pytz.timezone("Asia/Kolkata")  # ✅ Correct
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

        # Fetch restaurant policy
        restaurant = db.session.get(Restaurant, booking.restaurant_id)
        if not restaurant or not restaurant.policy:
            return {"message": "Restaurant policy not found."}, 404

        cancellation_threshold = restaurant.policy.cancellation_threshold  # Time in minutes

        # Compute current time and booking start time
        local_tz = pytz.timezone("Asia/Kolkata")  # Assuming IST as the system timezone
        now = datetime.now(local_tz)

        booking_datetime = datetime.combine(
            booking.date, datetime.strptime(booking.start_time, "%H:%M").time()
        )
        booking_datetime = local_tz.localize(booking_datetime)

        # Ensure cancellation is within allowed time
        min_cancellation_time = booking_datetime - timedelta(minutes=cancellation_threshold)
        if now >= min_cancellation_time:
            return {"message": "Booking cannot be canceled within the cancellation threshold."}, 400

        # Update status to 'canceled'
        booking.status = "canceled"

        # Release booked tables
        for table in booking.tables:
            db.session.delete(table)  # Remove from BookingTable association

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
    """Fetch all bookings of a user (active, cancelled, and completed)."""

    user_id = get_jwt_identity()  # Get logged-in user's ID
    current_time = datetime.utcnow().replace(tzinfo=pytz.utc)  # Get current time in UTC

    # Fetch all bookings for the user
    bookings = Booking.query.filter_by(user_id= user_id).all()
    
    booking_list = []
    for booking in bookings:
        # Fetch restaurant policy to determine reservation duration
        restaurant_policy = RestaurantPolicy.query.filter_by(id=booking.restaurant_id).first()
        reservation_duration = restaurant_policy.reservation_duration if restaurant_policy else 0

        # Calculate booking end time (start_time + reservation_duration)
        start_time_obj = datetime.strptime(booking.start_time, "%H:%M").time()
        booking_datetime = datetime.combine(booking.date, start_time_obj).replace(tzinfo=pytz.utc)
        end_time = booking_datetime + timedelta(minutes=reservation_duration)

        booking_list.append({
            "id": booking.id,
            "restaurant_id": booking.restaurant_id,
            "date": booking.date.strftime("%Y-%m-%d"),
            "start_time": booking.start_time,
            "guest_count": booking.guest_count,
            "status": booking.status,
            "created_at": booking.created_at.isoformat(),
        })

    return {"bookings": booking_list, "message":"order details fetched successfully", "status":200}, 200





def mark_booking_completed(app,booking_id):
    with app.app_context():
        booking = Booking.query.get(booking_id)
        if booking and booking.status == "active":
            booking.status = "completed"
            db.session.commit()
            print(f"Booking {booking_id} marked as completed.")




