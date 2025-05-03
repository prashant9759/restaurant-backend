from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import request
from app import db
from app.models import  (
    FoodOfferingPeriod, User,
    DietaryType
)
    
from app.schemas import (
    FoodOfferingPeriodSchema,
    FoodDietaryTypeSchema
)
from datetime import datetime

blp = Blueprint("food_management_api", __name__, url_prefix="/api/foods")

@blp.route("/time-periods")
class OfferingPeriodAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodOfferingPeriodSchema)
    def post(self, data):
        """Define a time-based offering period (e.g., Breakfast)."""
        user_id = get_jwt_identity()
        claims = get_jwt()

        if claims.get("role") != "staff":
            abort(403, message="Only staff can define time periods.")

        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            return {"message": "Staff not found."}, 404

        name = data["name"]
        start_time = datetime.strptime(data["start_time"], "%H:%M").time()
        end_time = datetime.strptime(data["end_time"], "%H:%M").time()

        # Ensure unique per restaurant
        existing = FoodOfferingPeriod.query.filter_by(
            name=name,
            restaurant_id=user.restaurant_id
        ).first()
        if existing:
            return {"message": "Offering with this name already exists."}, 400

        new_period = FoodOfferingPeriod(
            name=name,
            start_time=start_time,
            end_time=end_time,
            restaurant_id=user.restaurant_id
        )

        db.session.add(new_period)
        db.session.commit()

        return {"message": f"{name} period added successfully."}, 201
    
    def get(self):
        """List all dietary types."""
        restaurant_id = request.args.get("restaurant_id")
        if not restaurant_id:
            abort(400, message="Restaurant Id is required.")
        
        types = FoodOfferingPeriod.query.filter_by(is_deleted=False,restaurant_id=restaurant_id).all()
        return FoodOfferingPeriodSchema(many=True).dump(types), 200



@blp.route("/dietary-types")
class DietaryTypeAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodDietaryTypeSchema)
    def post(self, data):
        """Add a dietary category like Veg, Non-Veg, Vegan, etc."""
        user_id = get_jwt_identity()
        claims = get_jwt()
        if claims.get("role") != "staff":
            abort(403, message="Only staff can define dietary types.")
            
        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            return {"message": "Staff not found."}, 404

        # Check for duplicate
        if DietaryType.query.filter_by(name=data["name"].strip(), is_deleted=False).first():
            return {"message": "Dietary type already exists."}, 400
        

        new_type = DietaryType(
            name=data["name"].strip(),
            description=data.get("description", ""),
            restaurant_id=user.restaurant_id
        )
        db.session.add(new_type)
        db.session.commit()
        return {"message": f"{new_type.name} dietary type added."}, 201

    def get(self):
        """List all dietary types."""
        restaurant_id = request.args.get("restaurant_id")
        if not restaurant_id:
            abort(400, message="Restaurant Id is required.")
        
        types = DietaryType.query.filter_by(is_deleted=False,restaurant_id=restaurant_id).all()
        return FoodDietaryTypeSchema(many=True).dump(types), 200


