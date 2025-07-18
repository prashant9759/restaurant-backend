from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import exists


from app import db

from app.models import TableInstance, TableType, Restaurant, Booking, BookingTable
from app.schemas import TableSchema
from app.models import TableAvailability
from app.tasks import update_table_availability, schedule_daily_updates
from datetime import datetime, timedelta


blp = Blueprint("tables", __name__, url_prefix="/api/admins/restaurants")


def check_admin_role():
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")


def verify_admin_ownership(admin_id, restaurant_id):
    is_owner = db.session.query(
        exists().where(Restaurant.id == restaurant_id).where(
            Restaurant.admin_id == admin_id).where(Restaurant.is_deleted == False)
    ).scalar()

    if not is_owner:
        abort(403, message="You do not have permission to modify this restaurant.")


def verify_table_type_in_restaurant(restaurant_id, table_type_id):
    table_type_exists = db.session.query(
        exists().where(
            TableType.id == table_type_id,
            TableType.restaurant_id == restaurant_id,
            TableType.is_deleted == False  # Ensure table_type is not deleted
        )
    ).scalar()

    if not table_type_exists:
        abort(404, message="Table type not found or has been deleted.")


@blp.route("/<int:restaurant_id>/tables")
class TableListResource(MethodView):
    @jwt_required()
    @blp.arguments(TableSchema(many=True))
    def post(self, tables_data, restaurant_id):
        """Create multiple tables for a restaurant, handling partial failures."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        created_tables = []
        failed_tables = []
        total_added_capacity = 0

        for data in tables_data:
            try:
                table_type = db.session.query(TableType).filter(
                    TableType.id == data["table_type_id"],
                    TableType.restaurant_id == restaurant_id,
                    TableType.is_deleted == False  # Ensure table_type is not deleted
                ).first()

                if not table_type:
                    failed_tables.append(
                        {"data": data, "error": "table_type not found"})
                    continue
                if data["capacity"] > table_type.maximum_capacity or data["capacity"] < table_type.minimum_capacity:
                    failed_tables.append(
                        {"data": data, "error": "capacity is not within the range"})
                    continue

                exists = TableInstance.query.join(TableType).filter(
                    TableInstance.is_deleted == False,
                    TableInstance.table_number == data["table_number"],
                    TableType.restaurant_id == restaurant_id
                ).first() is not None

                if exists:
                    failed_tables.append(
                        {"data": data, "error": "A table with the same table number already exists in this restaurant"})
                    continue

                table = TableInstance(**data)
                db.session.add(table)
                created_tables.append(table)
                total_added_capacity += data["capacity"]
            except IntegrityError as e:
                db.session.rollback()
                failed_tables.append({"data": data, "error": str(e.orig)})

        # Commit only the successfully added tables
        db.session.commit()

        # Construct response
        if failed_tables:
            return {
                "successful": [table.to_dict() for table in created_tables],
                "failed": failed_tables,
                "message": "Some tables couldn't be created due to errors.",
                "status": 207  # 207 Multi-Status for partial success
            }, 207

        return {
            "data": [table.to_dict() for table in created_tables],
            "message": "All tables created successfully.",
            "status": 201
        }, 201

    @jwt_required()
    def get(self, restaurant_id):
        """Get all available (non-deleted) tables for a restaurant."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        tables = (
            db.session.query(
                TableInstance.id,
                TableInstance.table_number,
                TableInstance.is_available,
                TableInstance.is_deleted,
                TableInstance.location_description,
                TableType.id.label("table_type_id"),
                TableType.name.label("table_type_name"),
                TableInstance.capacity,
            )
            # Explicit join with TableType
            .join(TableType, TableType.id == TableInstance.table_type_id)
            .filter(
                TableType.restaurant_id == restaurant_id,
                TableInstance.is_deleted == False,   # Ensure the table is not deleted
                TableType.is_deleted == False        # Ensure the table type is not deleted
            )
            .all()
        )
        table_list = [
            {
                "table_id": t.id,
                "table_number": t.table_number,
                "is_available": t.is_available,
                "is_deleted": t.is_deleted,
                "location_description": t.location_description,
                "table_type_id": t.table_type_id,
                "table_type_name": t.table_type_name,
                "capacity": t.capacity,
            }
            for t in tables
        ]

        return {"data": table_list, "message": "Available tables retrieved successfully", "status": 200}, 200


@blp.route("/<int:restaurant_id>/tables/<int:table_id>")
class TableResource(MethodView):
    @jwt_required()
    def get(self, restaurant_id, table_id):
        """Retrieve a specific table in a restaurant while preventing N+1 queries."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table = (
            db.session.query(
                TableInstance.id,
                TableInstance.table_number,
                TableInstance.is_available,
                TableInstance.capacity,
                TableInstance.is_deleted,
                TableInstance.location_description,
                TableType.id.label("table_type_id"),
                TableType.name.label("table_type_name")
            )
            # Explicit join with TableType
            .join(TableType, TableType.id == TableInstance.table_type_id)
            .filter(
                TableInstance.id == table_id,
                TableType.restaurant_id == restaurant_id,
                TableInstance.is_deleted == False,   # Ensure the table is not deleted
                TableType.is_deleted == False        # Ensure the table type is not deleted
            )
            .first_or_404(description="Table not found or has been deleted.")
        )
        res = {
            "table_id": table.id,
            "table_number": table.table_number,
            "is_available": table.is_available,
            "is_deleted": table.is_deleted,
            "location_description": table.location_description,
            "table_type_id": table.table_type_id,
            "table_type_name": table.table_type_name,
            "capacity": table.capacity,
        }
        return {"data": res, "message": "Table retrieved successfully", "status": 200}, 200

    @jwt_required()
    @blp.arguments(TableSchema(partial=True))
    def patch(self, update_data, restaurant_id, table_id):
        """Update a specific table."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        try:
            table = (
                TableInstance.query
                # Join to enforce restaurant_id check
                .join(TableType, TableInstance.table_type_id == TableType.id)
                .filter(
                    TableInstance.id == table_id,
                    TableInstance.is_deleted == False,
                    # Ensure table belongs to the correct restaurant
                    TableType.restaurant_id == restaurant_id,
                    TableType.is_deleted == False  # Ensure the associated table type is not deleted
                )
                .first_or_404(description="Table not found or has been deleted.")
            )

            # Check for duplicate `table_number` within the same restaurant (excluding the current table)
            if "table_number" in update_data:
                existing_table = (
                    TableInstance.query
                    # Join TableType
                    .join(TableType, TableType.id == TableInstance.table_type_id)
                    .filter(
                        # Filter by restaurant_id from TableType
                        TableType.restaurant_id == restaurant_id,
                        TableInstance.table_number == update_data["table_number"],
                        TableInstance.is_deleted == False,
                        TableInstance.id != table_id  # Ensure we are not checking against itself
                    )
                    .first()
                )

                if existing_table:
                    return {"status": 400, "error": f"A table with number '{update_data['table_number']}' already exists in this restaurant."}, 400

            # If `table_type_id` is being updated, verify its validity
            if "table_type_id" in update_data:
                verify_table_type_in_restaurant(
                    restaurant_id, update_data["table_type_id"])

            if "is_available" in update_data:
                if update_data["is_available"]:
                    table.unavailable_from = None

            # Update table fields dynamically
            for key, value in update_data.items():
                setattr(table, key, value)

            db.session.commit()
            return {"data": table.to_dict(), "message": "Table updated successfully", "status": 200}, 200

        except SQLAlchemyError as e:
            db.session.rollback()
            abort(500, message=f"Database error: {str(e)}")

        except Exception as e:
            db.session.rollback()
            abort(400, message=f"An unexpected error occurred: {str(e)}")

    @jwt_required()
    @blp.response(204)
    def delete(self, restaurant_id, table_id):
        """Delete a specific table after ensuring it is not used in any active booking."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        try:
            table = (
                TableInstance.query
                # Join to enforce restaurant_id check
                .join(TableType, TableInstance.table_type_id == TableType.id)
                .filter(
                    TableInstance.id == table_id,
                    TableInstance.is_deleted == False,
                    # Ensure table belongs to the correct restaurant
                    TableType.restaurant_id == restaurant_id,
                    TableType.is_deleted == False  # Ensure the associated table type is not deleted
                )
                .first_or_404(description="Table not found or has been deleted.")
            )

            # Check if the table is being used in an active booking
            active_booking_exists = (
                db.session.query(BookingTable)
                # Join Booking on booking_id
                .join(Booking, Booking.id == BookingTable.booking_id)
                .filter(
                    BookingTable.table_id == table.id,  # Check if the table is in BookingTable
                    Booking.status == "active"  # Ensure booking is active
                )
                .first()
            )

            if active_booking_exists:
                abort(400, message="Cannot delete table as it is currently booked.")

            # Soft delete the table (instead of hard deleting)
            table.is_deleted = True
            db.session.commit()
            return {"message": "Table deleted successfully", "status": 204}, 204

        except SQLAlchemyError as e:
            db.session.rollback()
            abort(500, message=f"Database error: {str(e)}")

        except Exception as e:
            db.session.rollback()
            abort(400, message=f"An unexpected error occurred: {str(e)}")


@blp.route("/test-availability-update")
class TestAvailabilityUpdate(MethodView):
    @blp.response(200)
    def post(self):
        """Test endpoint to trigger table availability updates"""
        try:
            # Get a test table
            table = TableInstance.query.filter_by(is_deleted=False).first()
            if not table:
                abort(404, message="No active tables found")

            # Test single slot update
            now = datetime.now()
            update_table_availability.delay(table.id, now.date(), now)

            # Test daily schedule
            schedule_daily_updates.delay()

            return {"message": "Test updates triggered successfully"}
        except Exception as e:
            abort(500, message=str(e))


@blp.route("/test-single-update/<int:table_id>")
class TestSingleUpdate(MethodView):
    @blp.response(200)
    def post(self, table_id):
        """Test endpoint to update availability for a specific table"""
        try:
            table = TableInstance.query.get_or_404(table_id)
            if table.is_deleted:
                abort(404, message="Table not found")

            # Test with current time
            now = datetime.now()
            update_table_availability.delay(table.id, now.date(), now)

            return {"message": f"Update triggered for table {table_id}"}
        except Exception as e:
            abort(500, message=str(e))
