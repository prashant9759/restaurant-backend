from sqlalchemy import text
from flask import Flask, jsonify
from flask_smorest import Api
from flask_jwt_extended import JWTManager
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

import os
import sys
from dotenv import load_dotenv

from datetime import datetime, time, timedelta

from .db import db
from .celery_config import make_celery

from .models import (
    CuisineType, CuisineEnum, FoodPreferenceType, FoodPreferenceEnum, 
    Restaurant, DailyStats, HourlyStats, TableInstance,
    RestaurantOperatingHours
)


from .scheduler import scheduler
from apscheduler.triggers.cron import CronTrigger

from .controllers.user import blp as UserBlp
from .controllers.admin import blp as AdminBlp
from .controllers.restaurant import blp as RestaurantBlp
from .controllers.tableType import blp as tableTypeBlp
from .controllers.tableInstance import blp as tableBlp
from .controllers.presentation import blp as PresentationBlp
from .controllers.user_restaurant import blp as UserRestaurantBlp
from .controllers.adminDashboard import blp as AdminDashboardBlp
from .services.logout import is_token_revoked

load_dotenv()  # Load environment variables from .env file


def create_app():

    app = Flask(__name__)
    cors = CORS(app)
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.config["API_TITLE"] = "Restaurant Table Reservation API"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/"  # Ensures API docs are served
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["DEBUG"] = True
    
    app.config["CELERY_CONFIG"]={
     'broker_url': 'redis://localhost:6379/0',  # Broker (Redis or RabbitMQ)
     'result_backend': 'redis://localhost:6379/0'
     }

    db.init_app(app)
    celery = make_celery(app)

    # Initialize JWT
    app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
    jwt = JWTManager(app)



    @jwt.token_in_blocklist_loader
    def check_if_token_in_blocklist(jwt_header, jwt_payload):
        return is_token_revoked(jwt_payload)


    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "message": "The token has expired.",
            "error": "token_expired"
        }), 401


    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "message": "Signature verification failed.",
            "error": "invalid_token"
        }), 401


    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "description": "Request doesn't contain an access token.",
            "error": "authorization_required"
        }), 401


    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Customize Flask error responses"""
        print(e)
        response = e.get_response()
        print(response)
        response.data = jsonify({
            "code": e.code,
            "status": e.name,
            "message": e.description if isinstance(e.description, str) else e.description.get("message"),
        }).data
        response.content_type = "application/json"
        print(response.data)
        return response


    api = Api(app)
    api.register_blueprint(UserBlp)
    api.register_blueprint(AdminBlp)
    api.register_blueprint(RestaurantBlp)
    api.register_blueprint(tableTypeBlp)
    api.register_blueprint(tableBlp)
    api.register_blueprint(PresentationBlp)
    api.register_blueprint(UserRestaurantBlp)
    api.register_blueprint(AdminDashboardBlp)


    @app.route('/')
    def home():
        return jsonify({"message": "Welcome to the Restaurant Management API!"})


    def seed_cuisines_and_food_preferences():
        # Seeding Cuisines
        for cuisine in CuisineEnum:
            existing_cuisine = CuisineType.query.filter_by(
                name=cuisine.value).first()
            if not existing_cuisine:
                new_cuisine = CuisineType(name=cuisine.value)
                db.session.add(new_cuisine)
                # print(f"Added Cuisine: {cuisine.value}")
            # else:
            #     print(f"Already exists: {cuisine.value}")

        # Seeding Food Preferences
        for preference in FoodPreferenceEnum:
            existing_preference = FoodPreferenceType.query.filter_by(
                name=preference.value).first()
            if not existing_preference:
                new_preference = FoodPreferenceType(name=preference.value)
                db.session.add(new_preference)
                # print(f"Added Food Preference: {preference.value}")
            # else:
            #     print(f"Already exists: {preference.value}")

        # Commit changes
        try:
            db.session.commit()
            # print("✅ All cuisines and food preferences seeded successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error seeding cuisines and food preferences: {e}")






    def drop_all_tables():
        """Drops all tables in the database irrespective of foreign keys."""
        db.session.commit()  # Ensure all pending transactions are committed

        with db.engine.connect() as connection:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))  # ✅ Use text()

        db.reflect()  # Reflect all tables from the database
        db.drop_all()  # Drop all tables

        with db.engine.connect() as connection:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))  # ✅ Use text()

        print("All tables dropped successfully!")



    def get_working_restaurants(day_offset=0):
        """Get all restaurants that are working on a given day offset."""
        target_date = (datetime.utcnow() + timedelta(days=day_offset)).date()
        weekday = target_date.weekday()  # Monday=0, Sunday=6

        with app.app_context():
            restaurants = db.session.query(Restaurant).options(
                joinedload(Restaurant.policy),
                joinedload(Restaurant.operating_hours)
            ).join(
                RestaurantOperatingHours
            ).filter(
                Restaurant.is_deleted == False,
                RestaurantOperatingHours.day_of_week == weekday
            ).all()

            return restaurants





    # def calculate_daily_stats():
    #     """Runs at midnight to calculate the daily stats for yesterday's open restaurants."""
    #     yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    #     restaurants = get_working_restaurants(day_offset=-1)

    #     updated_count = 0  # Track successful updates

    #     with app.app_context():
    #         for restaurant in restaurants:
    #             try:
    #                 # Ensure the restaurant has a policy before proceeding
    #                 if not restaurant.policy:
    #                     print(f"Skipping restaurant {restaurant.id} due to missing policy.")
    #                     continue

    #                 # Ensure DailyStats entry doesn't already exist
    #                 if DailyStats.query.filter_by(restaurant_id=restaurant.id, date=yesterday).first():
    #                     print(f"DailyStats already exists for restaurant {restaurant.id} on {yesterday}.")
    #                     continue
                    
    #                 # Aggregate stats at the query level
    #                 stats = db.session.query(
    #                     func.coalesce(func.sum(HourlyStats.total_reservations), 0),
    #                     func.coalesce(func.sum(HourlyStats.total_cancelled_reservations), 0),
    #                     func.coalesce(func.sum(HourlyStats.total_revenue), 0.0),
    #                     func.coalesce(func.sum(HourlyStats.maximum_occupancy), 0),
    #                     func.coalesce(func.sum(HourlyStats.reserved_occupancy), 0),
    #                     func.coalesce(func.sum(HourlyStats.total_refund), 0),
    #                 ).filter(
    #                     HourlyStats.restaurant_id == restaurant.id,
    #                     HourlyStats.date == yesterday
    #                 ).first()

    #                 # Unpacking aggregated values
    #                 total_reservations, total_cancelled_reservations, total_revenue, \
    #                 maximum_occupancy, reserved_occupancy, total_refund = stats


    #                 # Create new DailyStats entry
    #                 daily_stat = DailyStats(
    #                     restaurant_id=restaurant.id,
    #                     date=yesterday,
    #                     total_reservations=total_reservations,
    #                     total_cancelled_reservations=total_cancelled_reservations,
    #                     total_revenue=total_revenue,
    #                     maximum_occupancy=maximum_occupancy,
    #                     reserved_occupancy=reserved_occupancy,
    #                     total_refund = total_refund,
    #                 )
    #                 db.session.add(daily_stat)
    #                 updated_count += 1  # Increment successful updates

    #             except SQLAlchemyError as e:
    #                 db.session.rollback()  # Rollback any changes for this restaurant
    #                 print(f"Error processing restaurant {restaurant.id}: {str(e)}")

    #         # Commit all successfully added entries
    #         try:
    #             db.session.commit()
    #             print(f"[{datetime.utcnow()}] DailyStats updated for {updated_count} restaurants")
    #         except SQLAlchemyError as e:
    #             db.session.rollback()
    #             print(f"Critical error committing DailyStats: {str(e)}")

    #         # Schedule hourly stats for today's working restaurants
    #         schedule_hourly_stats()
    #         print(f"[{datetime.utcnow()}] Hourly stats scheduled.")



    def calculate_hourly_stats(restaurant_id, date, time_str):
        """Calculates maximum occupancy for a given restaurant at a specific time (HH:MM)."""
        with app.app_context():
            restaurant = Restaurant.query.get(restaurant_id)
            if not restaurant:
                return

            # Calculate maximum occupancy dynamically
            max_occupancy = db.session.query(func.sum(TableInstance.capacity)).filter(
                TableInstance.restaurant_id == restaurant_id,
                TableInstance.is_deleted == False,
                TableInstance.is_available == True
            ).scalar() or 0  # Default to 0 if no tables found

            # Check if an entry already exists for this exact time (HH:MM)
            hourly_stat = HourlyStats.query.filter_by(
                restaurant_id=restaurant_id, date=date, time=time_str
            ).first()

            if hourly_stat:
                # Update existing entry
                hourly_stat.maximum_occupancy = max(max_occupancy,hourly_stat.reserved_occupancy)
            else:
                # Create a new entry
                hourly_stat = HourlyStats(
                    restaurant_id=restaurant_id,
                    date=date,
                    time=time_str,  # Store as 'HH:MM'
                    maximum_occupancy=max_occupancy
                )
                db.session.add(hourly_stat)

            db.session.commit()

            print(f"[{datetime.utcnow()}] HourlyStats updated for Restaurant {restaurant_id} at {time_str} with max occupancy   {max_occupancy}")




    def schedule_hourly_stats():
        """Schedules hourly stats for restaurants open today."""
        today = datetime.utcnow().date()
        weekday = today.weekday()  # Monday=0, Sunday=6
        with app.app_context():
            restaurants = get_working_restaurants(day_offset=0)

            scheduled_count = 0  # Count successful schedules

            for restaurant in restaurants:
                try:
                    if not restaurant.policy:
                        print(f"Skipping restaurant {restaurant.id} due to missing policy.")
                        continue
                    
                    # Fetch today's operating hours
                    operating_hours = next((oh for oh in restaurant.operating_hours if oh.day_of_week == str(weekday)), None)
                    if not operating_hours:
                        print(f"Skipping restaurant {restaurant.id}: No operating hours found for today.")
                        continue

                    open_time = datetime.combine(today, operating_hours.opening_time)
                    close_time = datetime.combine(today, operating_hours.closing_time)
                    interval = restaurant.policy.reservation_duration  # Get reservation duration

                    if not interval or interval <= 0:
                        print(f"Skipping restaurant {restaurant.id}: Invalid reservation duration.")
                        continue

                    # Schedule jobs at interval duration
                    current_time = open_time
                    while (current_time + timedelta(minutes=interval)) <= close_time:
                        formatted_time = current_time.strftime("%H:%M")  # Convert to HH:MM
                        job_id = f"hourly_stats_{restaurant.id}_{formatted_time.replace(':', '_')}"

                        scheduler.add_job(
                            id=job_id,
                            func=calculate_hourly_stats,
                            args=[restaurant.id, today, formatted_time],  # Pass HH:MM string
                            trigger="date",
                            run_date=current_time
                        )
                        current_time += timedelta(minutes=interval)

                    scheduled_count += 1  # Increment successful schedules

                except SQLAlchemyError as e:
                    print(f"Error scheduling hourly stats for restaurant {restaurant.id}: {str(e)}")

            print(f"[{datetime.utcnow()}] HourlyStats scheduled for {scheduled_count} restaurants.")





    port = int(os.getenv("PORT", 5000))  # Default to 5000 if PORT is not set


    with app.app_context():
        db.create_all()
        seed_cuisines_and_food_preferences()
        
        # Schedule the daily stats job to run at midnight
        
        scheduler.add_job(
            id="daily_stats",
            func=schedule_hourly_stats,
            trigger=CronTrigger(hour=0, minute=0)  # Runs at 12:00 AM every day
        )
        scheduler.start()
        print("Api running on port : {} ".format(port))
        
        return app, celery , port
