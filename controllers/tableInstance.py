from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import exists

from db import db

from models import TableInstance, TableType, Restaurant
from schemas import TableSchema

blp = Blueprint("tables", __name__, url_prefix="/api/admins/restaurants")


def check_admin_role():
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")


def verify_admin_ownership(admin_id, restaurant_id):
    is_owner = db.session.query(
        exists().where(Restaurant.id == restaurant_id).where(Restaurant.admin_id == admin_id)
    ).scalar()

    if not is_owner:
        abort(403, message="You do not have permission to modify this restaurant.")

def verify_table_type_in_restaurant(restaurant_id, table_type_id):
    table_type_exists = db.session.query(
        exists().where(TableType.id == table_type_id).where(TableType.restaurant_id == restaurant_id)
    ).scalar()

    if not table_type_exists:
        abort(400, message=f"TableType with id {table_type_id} does not belong to this restaurant.")



@blp.route("/<int:restaurant_id>/tables")
class TableListResource(MethodView):
    @jwt_required()
    @blp.arguments(TableSchema(many=True))
    def post(self, tables_data, restaurant_id):
        """Create multiple tables for a restaurant."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        created_tables = []
        try:
            for data in tables_data:
                verify_table_type_in_restaurant(restaurant_id, data["table_type_id"])
                table = TableInstance(**data)
                db.session.add(table)
                created_tables.append(table)

            db.session.commit()
            return {"data": [table.to_dict() for table in created_tables], "message": "Tables created successfully", "status": 201}, 201
        except IntegrityError as e:
            db.session.rollback()
            abort(400, message=f"Integrity error while creating tables: {str(e.orig)}")

    @jwt_required()
    def get(self, restaurant_id):
        """Get all tables for a restaurant."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        tables = TableInstance.query.join(TableType).filter(TableType.restaurant_id == restaurant_id).all()
        return {"data": [table.to_dict() for table in tables], "message": "Tables fetched successfully", "status": 200}, 200


@blp.route("/<int:restaurant_id>/tables/<int:table_id>")
class TableResource(MethodView):
    @jwt_required()
    def get(self, restaurant_id, table_id):
        """Get a specific table."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table = TableInstance.query.get_or_404(table_id)
        if table.table_type.restaurant_id != restaurant_id:
            abort(404, message="Table not found in this restaurant.")

        return {"data": table.to_dict(), "message": "Table fetched successfully", "status": 200}, 200

    @jwt_required()
    @blp.arguments(TableSchema(partial=True))
    def patch(self, update_data, restaurant_id, table_id):
        """Update a specific table."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table = TableInstance.query.get_or_404(table_id)
        if table.table_type.restaurant_id != restaurant_id:
            abort(404, message="Table not found in this restaurant.")

        if "table_type_id" in update_data:
            verify_table_type_in_restaurant(restaurant_id, update_data["table_type_id"])

        for key, value in update_data.items():
            setattr(table, key, value)

        db.session.commit()
        return {"data": table.to_dict(), "message": "Table updated successfully", "status": 200}, 200

    @jwt_required()
    @blp.response(204)
    def delete(self, restaurant_id, table_id):
        """Delete a specific table."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table = TableInstance.query.get_or_404(table_id)
        if table.table_type.restaurant_id != restaurant_id:
            abort(404, message="Table not found in this restaurant.")

        db.session.delete(table)
        db.session.commit()
        return "Table deleted successfully."
