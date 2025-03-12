

from project.db import db
from celery import shared_task
from project.models import Booking, BookingTable, TableInstance, TableType, HourlyStats
from sqlalchemy.sql.functions import func, coalesce



@shared_task(bind=True)
def update_hourly_entry(self, booking_id,is_cancelled, penalty=None):
    """Update hourly stats for a booking."""
    print(f"Updating hourly_entry for booking_id: {booking_id}")
    if is_cancelled:
        print(f"penalty is {penalty}")

    try:
        # Fetch required data in a single query
        result = (
            db.session.query(
                Booking.restaurant_id,
                Booking.date,
                Booking.start_time.label("time"),
                Booking.total_cost.label("total_revenue"),
                coalesce(func.sum(TableInstance.capacity), 0).label("reserved_occupancy"),
            )
            .join(BookingTable, Booking.id == BookingTable.booking_id)
            .join(TableInstance, BookingTable.table_id == TableInstance.id)
            .filter(Booking.id == booking_id)
            .group_by(Booking.restaurant_id, Booking.date, Booking.status, Booking.start_time)
            .first()
        )

        if not result:
            print(f"⚠️ Booking {booking_id} not found or has no tables.")
            return "Booking not found"

        restaurant_id, date, time, total_revenue, reserved_occupancy = result

        print(f"📌 Booking Details -> Restaurant ID: {restaurant_id}, Date: {date}, Time: {time}, Revenue: {total_revenue}")

        # Check if an entry already exists in HourlyStats
        hourly_entry = HourlyStats.query.filter_by(
            restaurant_id=restaurant_id, date=date, time=time
        ).first()

        if hourly_entry:
            # Update existing entry
            if is_cancelled:
                hourly_entry.total_cancelled_reservations += 1
                hourly_entry.total_refund += (total_revenue-penalty) if penalty else 0 # Use explicit refund value
                hourly_entry.reserved_occupancy = max(hourly_entry.reserved_occupancy - reserved_occupancy, 0)
            else:
                hourly_entry.total_reservations += 1
                hourly_entry.total_revenue += total_revenue
                hourly_entry.reserved_occupancy += reserved_occupancy
        else:
            # Create a new entry
            hourly_entry = HourlyStats(
                restaurant_id=restaurant_id,
                date=date,
                time=time,
                total_reservations=1 ,
                total_cancelled_reservations=1 if is_cancelled else 0,
                reserved_occupancy=reserved_occupancy if not is_cancelled else 0,
                total_revenue=total_revenue ,
                total_refund=coalesce (total_revenue-penalty) if  is_cancelled else 0,
            )
            db.session.add(hourly_entry)

        db.session.commit()
        print(f"✅ Hourly entry updated for {restaurant_id} at {time} on {date}")

    except Exception as e:
        db.session.rollback()
        print(f"❌ Failed to update hourly_entry: {str(e)}")

    return "done"
