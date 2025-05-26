from celery import shared_task
from celery.contrib.abortable import AbortableTask
from datetime import datetime, timedelta, time
from app import db, celery
from app.models import (
    TableInstance, TableAvailability, RestaurantOperatingHours,
    Restaurant, RestaurantPolicy, FoodItem, FoodItemVariant, FoodItemStock
)
import logging
from celery.schedules import crontab
from redis.exceptions import ConnectionError as RedisConnectionError
from celery.exceptions import MaxRetriesExceededError
from flask import current_app

# Set up logging
logger = logging.getLogger(__name__)


def get_time_slots(start_time, end_time, interval_minutes):
    """Generate time slots between start and end time with given interval."""
    slots = []
    current = start_time
    while current < end_time:
        slots.append(current)
        current = (datetime.combine(datetime.today(), current) +
                   timedelta(minutes=interval_minutes)).time()
    return slots


@shared_task(bind=True, base=AbortableTask)
def update_table_availability(self, table_id, date, slot_time):
    """Update availability for a specific table and slot time."""
    try:
        logger.info(
            f"Updating availability for table {table_id} on {date} at {slot_time}")

        # Get the table
        table = TableInstance.query.get(table_id)
        if not table or table.is_deleted:
            logger.warning(f"Table {table_id} not found or deleted")
            return

        # Get or create table availability entry
        table_availability = TableAvailability.query.filter_by(
            table_id=table_id,
            date=date
        ).first()

        if not table_availability:
            table_availability = TableAvailability(
                table_id=table_id,
                date=date,
                available_slots=[]
            )
            db.session.add(table_availability)

        # Convert slot_time to string format if it's a time object
        slot_time_str = slot_time.strftime(
            '%H:%M') if isinstance(slot_time, time) else slot_time

        # Add slot to available_slots if not already present
        if slot_time_str not in table_availability.available_slots:
            table_availability.available_slots.append(slot_time_str)
            db.session.commit()
            logger.info(
                f"Added slot {slot_time_str} to available slots for table {table_id}")

    except Exception as e:
        logger.error(f"Error updating availability: {str(e)}")
        db.session.rollback()
        self.retry(exc=e, countdown=60)  # Retry after 1 minute


@shared_task(bind=True, base=AbortableTask)
def schedule_daily_updates(self):
    """Initialize daily availability for all restaurants and their tables."""
    try:
        logger.info("Starting daily availability updates")
        tomorrow = datetime.now().date() + timedelta(days=1)

        # Get all active restaurants
        restaurants = Restaurant.query.filter_by(is_deleted=False).all()
        logger.info(f"Found {len(restaurants)} active restaurants")

        for restaurant in restaurants:
            try:
                # Get operating hours for tomorrow
                operating_hours = RestaurantOperatingHours.query.filter_by(
                    restaurant_id=restaurant.id,
                    day_of_week=tomorrow.weekday()
                ).first()

                if not operating_hours:
                    logger.warning(
                        f"No operating hours found for restaurant {restaurant.id} on {tomorrow}")
                    continue

                # Get restaurant policy for reservation duration
                policy = RestaurantPolicy.query.filter_by(
                    restaurant_id=restaurant.id).first()
                if not policy:
                    logger.warning(
                        f"No policy found for restaurant {restaurant.id}")
                    continue

                # Get all tables for this restaurant
                tables = TableInstance.query.join(
                    TableInstance.table_type
                ).filter(
                    TableInstance.table_type.has(restaurant_id=restaurant.id),
                    TableInstance.is_deleted == False
                ).all()

                logger.info(
                    f"Found {len(tables)} tables for restaurant {restaurant.id}")

                # Generate time slots for the day using reservation_duration from policy
                time_slots = get_time_slots(
                    operating_hours.opening_time,
                    operating_hours.closing_time,
                    interval_minutes=policy.reservation_duration
                )

                # Schedule update_table_availability for each table and time slot
                for table in tables:
                    for slot_time in time_slots:
                        # Create datetime for the slot
                        slot_datetime = datetime.combine(tomorrow, slot_time)

                        # Schedule the task to run at the slot's start time
                        update_table_availability.apply_async(
                            args=[table.id, tomorrow, slot_time],
                            eta=slot_datetime
                        )
                        logger.info(
                            f"Scheduled availability update for table {table.id} at {slot_time}")

            except Exception as e:
                logger.error(
                    f"Error processing restaurant {restaurant.id}: {str(e)}")
                continue

        logger.info("Completed scheduling daily availability updates")

    except Exception as e:
        logger.error(f"Error in schedule_daily_updates: {str(e)}")
        self.retry(exc=e, countdown=300)  # Retry after 5 minutes


@shared_task(bind=True, base=AbortableTask)
def create_stock_entries(self):
    """Create stock entries for all restaurants and their food items."""
    try:
        logger.info("Starting stock entries creation for all restaurants")

        # Get all active restaurants
        restaurants = Restaurant.query.filter_by(is_deleted=False).all()
        logger.info(f"Found {len(restaurants)} active restaurants")

        for restaurant in restaurants:
            try:
                # Get all food items for this restaurant
                food_items = (
                    FoodItem.query
                    .join(FoodItem.category)
                    .filter(
                        FoodItem.category.has(restaurant_id=restaurant.id),
                        FoodItem.is_deleted == False
                    )
                    .all()
                )

                logger.info(
                    f"Found {len(food_items)} food items for restaurant {restaurant.id}")

                for food_item in food_items:
                    try:
                        if food_item.has_variants:
                            # Get all variants for this food item
                            variants = FoodItemVariant.query.filter_by(
                                food_item_id=food_item.id,
                                is_deleted=False
                            ).all()

                            for variant in variants:
                                # Check if stock entry already exists
                                existing_entry = FoodItemStock.query.filter_by(
                                    food_item_id=food_item.id,
                                    variant_id=variant.id
                                ).first()

                                if not existing_entry:
                                    # Create new stock entry for variant
                                    stock_entry = FoodItemStock(
                                        food_item_id=food_item.id,
                                        variant_id=variant.id,
                                        current_stock=0,  # Default to 0
                                        threshold=10  # Default threshold
                                    )
                                    db.session.add(stock_entry)
                                    logger.info(
                                        f"Created stock entry for food item {food_item.id} variant {variant.id}")
                        else:
                            # Check if stock entry already exists for non-variant item
                            existing_entry = FoodItemStock.query.filter_by(
                                food_item_id=food_item.id,
                                variant_id=None
                            ).first()

                            if not existing_entry:
                                # Create new stock entry for non-variant item
                                stock_entry = FoodItemStock(
                                    food_item_id=food_item.id,
                                    current_stock=0,  # Default to 0
                                    threshold=10  # Default threshold
                                )
                                db.session.add(stock_entry)
                                logger.info(
                                    f"Created stock entry for food item {food_item.id}")

                    except Exception as e:
                        logger.error(
                            f"Error processing food item {food_item.id}: {str(e)}")
                        continue

                # Commit changes for this restaurant
                db.session.commit()
                logger.info(
                    f"Completed stock entries creation for restaurant {restaurant.id}")

            except Exception as e:
                logger.error(
                    f"Error processing restaurant {restaurant.id}: {str(e)}")
                db.session.rollback()
                continue

        logger.info("Completed stock entries creation for all restaurants")

    except Exception as e:
        logger.error(f"Error in create_stock_entries: {str(e)}")
        self.retry(exc=e, countdown=300)  # Retry after 5 minutes

# Configure periodic tasks


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Schedule daily updates at midnight
    sender.add_periodic_task(
        crontab(hour=0, minute=0),  # Run at midnight
        schedule_daily_updates.s(),
        name='daily-midnight-update'
    )

    # Schedule stock entries creation daily at 1 AM
    sender.add_periodic_task(
        crontab(hour=1, minute=0),  # Run at 1 AM
        create_stock_entries.s(),
        name='daily-stock-entries-creation'
    )

    # # For testing: Run every minute
    # sender.add_periodic_task(
    #     crontab(minute='*'),  # Run every minute
    #     schedule_daily_updates.s(),
    #     name='test-minute-update'
    # )






