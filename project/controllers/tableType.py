from flask.views import MethodView  # Import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from flask import request, current_app
from sqlalchemy import func

from datetime import datetime, time

from project.db import db
from project.models import TableType, TableShape, Restaurant
from project.schemas import TableTypeSchema, UpdateFeatureSpecialitySchema
from project.services.helper import *

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
        table_types = TableType.query.filter(
            TableType.restaurant_id == restaurant_id, 
            TableType.is_deleted == False
        ).all()

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
        failed_entries = []

        try:
            for data in table_types_data:
                verify_admin_ownership(admin_id, restaurant_id)
                data["restaurant_id"] = restaurant_id

                # Check if a non-deleted table type with the same name already exists
                existing_table_type = TableType.query.filter_by(
                    restaurant_id=restaurant_id, 
                    name=data["name"], 
                    is_deleted=False
                ).first()

                if existing_table_type:
                    failed_entries.append({
                        "name": data["name"],
                        "error": f"A table type with name '{data['name']}' already exists in this restaurant."
                    })
                    continue  # Skip creating this entry and move to the next one

                try:
                    # Extract and create features
                    feature_names = data.pop("features", [])
                    feature_instances = [Feature(name=name) for name in feature_names]

                    # Convert shape to Enum
                    data["shape"] = TableShape(data["shape"])
                    table_type = TableType(**data, features=feature_instances)
                    db.session.add(table_type)
                    created_table_types.append(table_type)

                except Exception as e:
                    failed_entries.append({
                        "name": data["name"],
                        "error": f"Unexpected error: {str(e)}"
                    })

            db.session.commit()

        except IntegrityError as e:
            db.session.rollback()
            failed_entries.append({
                "error": f"Database integrity error: {str(e.orig)}"
            })

        response = {"status": 201}

        if created_table_types:
            response["data"] = [tableType.to_dict() for tableType in created_table_types]
            response["message"] = "Some or all table types created successfully."

        if failed_entries:
            response["failed"] = failed_entries
            response["message"] = "Some table types failed to create."

        return response, 201


@blp.route("/<int:restaurant_id>/table_types/<int:table_type_id>")
class TableTypeResource(MethodView):  # Inherit from MethodView
    
    @jwt_required()
    def get(self, restaurant_id, table_type_id):
        """Get a specific table type by ID."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table_type = TableType.query.filter_by(id=table_type_id, restaurant_id=restaurant_id, is_deleted=False).first()

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

        # Check if the table type exists and is not marked as deleted
        table_type = TableType.query.filter_by(id=table_type_id, is_deleted=False, restaurant_id=restaurant_id).first()
        if not table_type:
            abort(404, message="Table type not found or already deleted.")

        # Ensure that maximum_capacity >= minimum_capacity if both are provided
        min_cap = update_data.get("minimum_capacity", table_type.minimum_capacity)
        max_cap = update_data.get("maximum_capacity", table_type.maximum_capacity)

        if min_cap is not None and max_cap is not None and max_cap < min_cap:
            abort(400, message="Maximum capacity cannot be less than minimum capacity.")
            
        # Check if a non-deleted table type with the same name already exists
        existing_table_type = TableType.query.filter_by(
            restaurant_id=restaurant_id, 
            name=update_data["name"], 
            is_deleted=False,
        ).first()
        
        if existing_table_type and str(existing_table_type.id) != str(table_type_id):
            abort(400, message="A table with this name already exist")

        return update_logic(table_type,update_data,"table_type")


    @jwt_required()
    @blp.response(204)
    def delete(self, restaurant_id, table_type_id):
        """Delete a table type if it exists, is not deleted, and has no active bookings."""
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        # Check if the table type exists and is not marked as deleted
        table_type = TableType.query.filter_by(id=table_type_id, is_deleted=False, restaurant_id=restaurant_id).first()
        if not table_type:
            abort(404, message="Table type not found or already deleted.")

        # Check if any active booking exists for tables of this type
        active_booking_exists = (
            db.session.query(BookingTable)
            .join(TableInstance, TableInstance.id == BookingTable.table_id)
            .join(Booking, Booking.id == BookingTable.booking_id)  # Add this join!
            .filter(
                TableInstance.table_type_id == table_type_id,
                Booking.status == "active"
            )
            .first()
        )

        if active_booking_exists:
            abort(400, message="Cannot delete table type. Active bookings exist.")
            
        table_type.soft_delete()
        return {"message":"deletion successfull"}, 204



@blp.route("/<int:restaurant_id>/table_types/<int:table_type_id>/update-features")
class UpdateFeaturesSpecialities(MethodView):
    @jwt_required()
    @blp.arguments(UpdateFeatureSpecialitySchema)
    def put(self, data, restaurant_id,table_type_id):
        """
        Update (Add/Remove) Features & Specialities for a TableType.
        - **Add**: Always create new features/specialities, even if they exist.
        - **Remove**: Pass IDs to remove specific features/specialities.
        """
        check_admin_role()
        admin_id = get_jwt_identity()
        verify_admin_ownership(admin_id, restaurant_id)

        table_type = db.session.query(TableType)\
            .options(joinedload(TableType.features))\
            .filter(TableType.restaurant_id == restaurant_id, TableType.is_deleted == False )\
            .first()
        
        if not table_type:
            abort(404, message = "No such table type found")

        try:
            # Handle Features
            features_data = data.get("features", {})
            self.handle_features(table_type, features_data)

            db.session.commit()
            return {"message": "Features and specialities updated successfully"}, 200

        except SQLAlchemyError as e:
            db.session.rollback()
            abort(500, message=str(e))

    def handle_features(self, table_type, features_data):
        """Helper function to add/remove features."""
        if "add" in features_data:
            self.add_features(table_type, features_data["add"])
        if "remove" in features_data:
            self.remove_features(table_type, features_data["remove"])

    def add_features(self, table_type, feature_names):
        """Always create new features and link them to the table_type."""
        new_features = [Feature(name=name) for name in feature_names]
        db.session.add_all(new_features)  # Batch insert for better performance
        table_type.features.extend(new_features)

    def remove_features(self, table_type, feature_ids):
        """Remove features by ID efficiently using a batch query."""
        features_to_remove = Feature.query.filter(
            Feature.id.in_(feature_ids)).all()
        for feature in features_to_remove:
            if feature in table_type.features:
                table_type.features.remove(feature)
            db.session.delete(feature)



# Update Feature
@blp.route("/<int:restaurant_id>/table_types/<int:table_type_id>/features/<int:feature_id>", methods=["PATCH"])
@jwt_required()
def update_feature( restaurant_id ,table_type_id, feature_id):
    check_admin_role()
    admin_id = get_jwt_identity()
    
    verify_admin_ownership(admin_id, restaurant_id)

    table_type = db.session.query(TableType)\
        .filter(TableType.restaurant_id == restaurant_id, TableType.is_deleted == False )\
        .first()
    
    if not table_type:
        abort(404, message = "No such table type found")
        
    data = request.get_json()
    new_name = data.get("name")
    
    if not new_name:
        return {"error": "Feature name is required"}, 400
    
    
    feature = db.session.query(Feature).join(tableType_features).filter(
        Feature.id == feature_id, tableType_features.c.table_type_id == table_type_id
    ).first()
    
    if not feature:
        return {"error": "Feature not found in this table type"}, 404
    
    feature.name = new_name
    try:
        db.session.commit()
        return {"message": "Feature updated successfully"},200
    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500



