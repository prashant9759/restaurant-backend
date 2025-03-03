from flask.views import MethodView  # Import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError

from db import db
from models import TableType, TableShape, Restaurant
from schemas import TableTypeSchema
from services.helper import *

blp = Blueprint("table_types", __name__, url_prefix="/api/admins/restaurants")

def is_duplicate_table_type(name, restaurant_id):
    return TableType.query.filter_by(name=name, restaurant_id=restaurant_id).first() is not None

def check_admin_role():
    """Check if the JWT contains the 'admin' role."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")

def verify_admin_ownership(admin_id, restaurant_id):
    """Verify if the restaurant belongs to the admin."""
    restaurant = Restaurant.query.get(restaurant_id)
    if not restaurant or str(restaurant.admin_id) != str(admin_id):
        abort(403, message="You do not have permission to modify this restaurant.")

@blp.route("/<int:restaurant_id>/table_types")
class TableTypeListResource(MethodView):  # Inherit from MethodView
    
    @jwt_required()
    def get(self, restaurant_id):
        """Get all table types for a restaurant."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)
        table_types = TableType.query.filter_by(restaurant_id=restaurant_id).all()
        if not table_types or len(table_types) ==0:
            abort(404, message="No table_types found for this restaurant.")
        return {"data": [tableType.to_dict() for tableType in table_types], 
                "message": "All TableTypes fetched successfully", "status": 200}, 200
    
    @jwt_required()
    @blp.arguments(TableTypeSchema(many=True))
    def post(self, table_types_data, restaurant_id):
        """Create multiple table types."""
        check_admin_role()
        admin_id = get_jwt_identity()

        created_table_types = []
        try:
            for data in table_types_data:
                verify_admin_ownership(admin_id, restaurant_id)
                
                if is_duplicate_table_type(data["name"], restaurant_id):
                    abort(400, message=f"TableType with name '{data['name']}' already exists for this restaurant.")
                
                data["restaurant_id"] = restaurant_id

                # Convert shape to Enum
                data["shape"] = TableShape(data["shape"])
                table_type = TableType(**data)
                db.session.add(table_type)
                created_table_types.append(table_type)
            db.session.commit()
            return {"data": [tableType.to_dict() for tableType in created_table_types], 
                    "message": "TableTypes created successfully", "status": 201}, 201
        except IntegrityError as e:
            db.session.rollback()
            error_message = str(e.orig)
            abort(400, message=f"Integrity error while creating table types, the error is: {error_message}")

@blp.route("/<int:restaurant_id>/table_types/<int:table_type_id>")
class TableTypeResource(MethodView):  # Inherit from MethodView
    
    @jwt_required()
    def get(self, restaurant_id, table_type_id):
        """Get a specific table type by ID."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table_type = TableType.query.filter_by(id=table_type_id, restaurant_id=restaurant_id).first()

        if not table_type:
            abort(404, message="TableType not found for this restaurant.")

        return {"table_type":table_type.to_dict(), "message": "Table Type fetched successfully" , "status":200}, 200
    
    @jwt_required()
    @blp.arguments(TableTypeSchema(partial=True))
    def patch(self, update_data, restaurant_id, table_type_id):
        """Partially update a table type."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)
        return update_logic(table_type_id, TableType, update_data, "table type")

    @jwt_required()
    @blp.arguments(TableTypeSchema)
    def put(self, update_data, restaurant_id, table_type_id):
        """Fully update a table type."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)
        table_type = TableType.query.get_or_404(table_type_id)
        return update_logic(table_type, update_data, "table type")

    @jwt_required()
    @blp.response(204)
    def delete(self, restaurant_id, table_type_id):
        """Delete a table type."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)
        return delete_logic(table_type_id, TableType, "table type")
