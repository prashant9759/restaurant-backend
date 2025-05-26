from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import request
from app import db
from app.models import (
    FoodOfferingPeriod, User,
    DietaryType, FoodCategory,
    FoodItem, FoodItemVariant, Restaurant
)

from app.schemas import (
    FoodOfferingPeriodSchema,
    FoodDietaryTypeSchema,
    FoodCategorySchema,
    FoodItemSchema,
    FoodItemVariantSchema
)
from datetime import datetime
from werkzeug.exceptions import HTTPException
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from marshmallow import Schema, fields, validate, ValidationError


blp = Blueprint("food_management_api", __name__, url_prefix="/api/foods")


@blp.route("/offering-periods")
class OfferingPeriodAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodOfferingPeriodSchema(many=True))
    def post(self, data):
        """Define multiple time-based offering periods (e.g., Breakfast)."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can define time periods.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404

            # Get existing periods for duplicate checking
            existing_periods = {
                period.name.lower(): period
                for period in FoodOfferingPeriod.query.filter_by(
                    restaurant_id=user.restaurant_id,
                    is_deleted=False
                ).all()
            }

            new_periods = []
            for period_data in data:
                name = period_data["name"]
                if name.lower() in existing_periods:
                    continue

                start_time = datetime.strptime(
                    period_data["start_time"], "%H:%M").time()
                end_time = datetime.strptime(
                    period_data["end_time"], "%H:%M").time()

                new_period = FoodOfferingPeriod(
                    name=name,
                    start_time=start_time,
                    end_time=end_time,
                    restaurant_id=user.restaurant_id
                )
                new_periods.append(new_period)
                existing_periods[name.lower()] = new_period

            if new_periods:
                db.session.add_all(new_periods)
                db.session.commit()

            return {"message": f"{len(new_periods)} offering periods added successfully."}, 201

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            return {"message": f"Error creating offering periods: {str(e)}"}, 500

    def get(self):
        """List all offering periods."""
        try:
            restaurant_id = request.args.get("restaurant_id")
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            if not restaurant_id:
                abort(400, message="Restaurant Id is required.")

            periods = FoodOfferingPeriod.query.filter_by(
                is_deleted=False, restaurant_id=restaurant_id
            ).paginate(page=page, per_page=per_page)

            return {
                "items": FoodOfferingPeriodSchema(many=True).dump(periods.items),
                "total": periods.total,
                "pages": periods.pages,
                "current_page": periods.page
            }, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching offering period: {str(e)}")


@blp.route("/offering-periods/<int:offering_period_id>")
class ModifyOfferingPeriod(MethodView):
    @jwt_required()
    @blp.arguments(FoodOfferingPeriodSchema)
    def put(self, data, offering_period_id):
        """Modify a time-based offering period (e.g., Breakfast)."""
        print("inside")
        user_id = get_jwt_identity()
        claims = get_jwt()

        if claims.get("role") != "staff":
            abort(403, message="Only staff can define time periods.")

        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            return {"message": "Staff not found."}, 404

        try:
            offering_period = FoodOfferingPeriod.query.filter_by(
                id=offering_period_id,
                restaurant_id=user.restaurant_id
            ).first()

            if not offering_period:
                abort(
                    404, message="No entry corresponding to this Offering Period Id is found.")

            existing = FoodOfferingPeriod.query.filter(
                FoodOfferingPeriod.name == data["name"],
                FoodOfferingPeriod.restaurant_id == user.restaurant_id,
                FoodOfferingPeriod.id != offering_period_id
            ).first()

            if existing:
                return {"message": "Offering with this name already exists."}, 400

            name = data["name"]
            start_time = datetime.strptime(data["start_time"], "%H:%M").time()
            end_time = datetime.strptime(data["end_time"], "%H:%M").time()

            offering_period.name = name
            offering_period.start_time = start_time
            offering_period.end_time = end_time

            db.session.commit()

            return {"message": f"{name} period modified successfully."}, 200

        except Exception as e:
            db.session.rollback()  # Rollback the transaction in case of error
            return {"message": f"Error modifying offering period: {str(e)}"}, 500

    @jwt_required()
    def delete(self, offering_period_id):
        """Soft delete a food offering period."""
        user_id = get_jwt_identity()
        claims = get_jwt()

        if claims.get("role") != "staff":
            abort(403, message="Only staff can delete offering periods.")

        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            return {"message": "Staff not found."}, 404

        try:
            period = FoodOfferingPeriod.query.filter_by(
                id=offering_period_id,
                restaurant_id=user.restaurant_id,
                is_deleted=False
            ).first()

            if not period:
                return {"message": "Offering period not found."}, 404

            period.is_deleted = True
            # Remove associations to food items without deleting food items
            period.food_items.clear()
            db.session.commit()
            return {"message": f"{period.name} offering period deleted."}, 200

        except Exception as e:
            db.session.rollback()  # Rollback the transaction in case of error
            return {"message": f"Error deleting offering period: {str(e)}"}, 500

    @blp.response(200, FoodOfferingPeriodSchema)
    def get(self, offering_period_id):
        """Fetch a specific offering period."""
        try:
            restaurant_id = request.args.get("restaurant_id")
            if not restaurant_id:
                abort(400, message="Restaurant Id is required.")

            period = FoodOfferingPeriod.query.filter_by(
                id=offering_period_id,
                is_deleted=False,
                restaurant_id=restaurant_id
            ).first()

            if not period:
                abort(404, message="Offering period not found.")

            return period

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching offering period: {str(e)}")


@blp.route("/dietary-types")
class DietaryTypeAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodDietaryTypeSchema(many=True))
    def post(self, data):
        """Add multiple dietary categories like Veg, Non-Veg, Vegan, etc."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can define dietary types.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404

            # Get existing types for duplicate checking
            existing_types = {
                dt.name.lower(): dt
                for dt in DietaryType.query.filter_by(
                    restaurant_id=user.restaurant_id,
                    is_deleted=False
                ).all()
            }

            new_types = []
            for type_data in data:
                # Check for duplicate (case-insensitive)
                if type_data["name"].strip().lower() in existing_types:
                    continue

                new_type = DietaryType(
                    name=type_data["name"].strip(),
                    description=type_data.get("description", ""),
                    restaurant_id=user.restaurant_id
                )
                new_types.append(new_type)
                existing_types[type_data["name"].strip().lower()] = new_type

            if new_types:
                db.session.add_all(new_types)
                db.session.commit()

            return {"message": f"{len(new_types)} dietary types added."}, 201

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            return {"message": f"Error adding dietary types: {str(e)}"}, 500

    def get(self):
        """List all dietary types."""
        try:
            restaurant_id = request.args.get("restaurant_id")
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            if not restaurant_id:
                abort(400, message="Restaurant Id is required.")

            types = DietaryType.query.filter_by(
                is_deleted=False, restaurant_id=restaurant_id
            ).paginate(page=page, per_page=per_page)

            return {
                "items": FoodDietaryTypeSchema(many=True).dump(types.items),
                "total": types.total,
                "pages": types.pages,
                "current_page": types.page
            }, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching dietary types.: {str(e)}")


@blp.route("/dietary-types/<int:dietary_type_id>")
class ModifyDietaryType(MethodView):

    @jwt_required()
    @blp.arguments(FoodDietaryTypeSchema)
    def put(self, data, dietary_type_id):
        """Modify a dietary type (e.g., Vegan, Eggish)."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can define dietary types.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404

            dietary_type = DietaryType.query.filter_by(
                id=dietary_type_id,
                restaurant_id=user.restaurant_id
            ).first()

            if not dietary_type:
                abort(
                    404, message="No entry corresponding to this Dietary Type Id is found.")

            existing = DietaryType.query.filter(
                DietaryType.name == data["name"],
                DietaryType.restaurant_id == user.restaurant_id,
                DietaryType.id != dietary_type_id
            ).first()

            if existing:
                return {"message": "Dietary Type with this name already exists."}, 400

            # Update dietary type
            dietary_type.name = data["name"]
            dietary_type.description = data["description"]

            db.session.commit()

            return {"message": f"Dietary Type with name '{data['name']}' modified successfully."}, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            db.session.rollback()  # Rollback the transaction in case of error
            return {"message": f"Error modifying dietary type: {str(e)}"}, 500

    @blp.response(200, FoodDietaryTypeSchema)
    def get(self, dietary_type_id):
        """Fetch a specific dietary type."""
        try:
            restaurant_id = request.args.get("restaurant_id")
            if not restaurant_id:
                abort(400, message="Restaurant Id is required.")
            d_type = DietaryType.query.filter_by(
                id=dietary_type_id,
                is_deleted=False,
                restaurant_id=restaurant_id
            ).first()
            if not d_type:
                abort(404, message="Dietary type not found.")
            return d_type

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching food items: {str(e)}")

    @jwt_required()
    def delete(self, dietary_type_id):
        """Soft delete a dietary type."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can delete dietary types.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404

            d_type = DietaryType.query.filter_by(
                id=dietary_type_id,
                restaurant_id=user.restaurant_id,
                is_deleted=False
            ).first()

            if not d_type:
                return {"message": "Dietary type not found."}, 404

            # Soft delete the dietary type
            d_type.is_deleted = True
            # Remove associations to food items without deleting food items
            d_type.food_items.clear()
            db.session.commit()

            return {"message": f"{d_type.name} dietary type deleted."}, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            db.session.rollback()  # Rollback the transaction in case of error
            return {"message": f"Error deleting dietary type: {str(e)}"}, 500


@blp.route("/categories")
class FoodCategoryAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodCategorySchema(many=True))
    def post(self, data):
        """Add multiple food categories like Daal, Chapati, Bhurgi, etc."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can define dietary types.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return {"message": "Staff not found."}, 404

            # Get existing categories for duplicate checking
            existing_categories = {
                cat.name.lower(): cat
                for cat in FoodCategory.query.filter_by(
                    restaurant_id=user.restaurant_id,
                    is_deleted=False
                ).all()
            }

            new_categories = []
            for category_data in data:
                # Check for duplicate (case-insensitive)
                if category_data["name"].strip().lower() in existing_categories:
                    continue

                new_category = FoodCategory(
                    name=category_data["name"].strip(),
                    description=category_data.get("description", ""),
                    restaurant_id=user.restaurant_id
                )
                new_categories.append(new_category)
                existing_categories[category_data["name"].strip(
                ).lower()] = new_category

            if new_categories:
                db.session.add_all(new_categories)
                db.session.commit()

            return {"message": f"{len(new_categories)} food categories added."}, 201

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            return {"message": f"Error creating food categories: {str(e)}"}, 500

    def get(self):
        """List all food categories."""
        try:
            restaurant_id = request.args.get("restaurant_id")
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            if not restaurant_id:
                abort(400, message="Restaurant Id is required.")

            categories = FoodCategory.query.filter_by(
                is_deleted=False, restaurant_id=restaurant_id
            ).paginate(page=page, per_page=per_page)

            return {
                "items": FoodCategorySchema(many=True).dump(categories.items),
                "total": categories.total,
                "pages": categories.pages,
                "current_page": categories.page
            }, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching food items: {str(e)}")


@blp.route("/categories/<int:category_id>")
class ModifyFoodCategory(MethodView):

    @jwt_required()
    @blp.arguments(FoodCategorySchema)
    def put(self, data, category_id):
        """Modify a food category (e.g., Chapati)."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can modify food categories.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            category = FoodCategory.query.filter_by(
                id=category_id,
                restaurant_id=user.restaurant_id
            ).first()

            if not category:
                abort(
                    404, message="No entry corresponding to this Food Category ID is found.")

            existing = FoodCategory.query.filter(
                FoodCategory.name == data["name"],
                FoodCategory.restaurant_id == user.restaurant_id,
                FoodCategory.id != category_id
            ).first()
            if existing:
                abort(400, message="Food Category with this name already exists.")

            category.name = data["name"]
            category.description = data.get("description")

            db.session.commit()
            return {"message": f"Food Category with name '{category.name}' modified successfully."}, 200

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Error updating category: {str(e)}")

    @jwt_required()
    def delete(self, category_id):
        """Soft delete a food category."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can delete food categories.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            category = FoodCategory.query.filter_by(
                id=category_id,
                restaurant_id=user.restaurant_id,
                is_deleted=False
            ).first()

            if not category:
                abort(404, message="Food Category not found.")

            # Soft delete food items and their variants
            for item in category.food_items:
                item.is_deleted = True
                for variant in item.variants:
                    variant.is_deleted = True

            category.is_deleted = True
            db.session.commit()
            return {"message": f"{category.name} Food Category deleted."}, 200

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Error deleting category: {str(e)}")

    @blp.response(200, FoodCategorySchema)
    def get(self, category_id):
        """Fetch a single food category by ID."""
        try:
            restaurant_id = request.args.get("restaurant_id", type=int)

            if not restaurant_id:
                abort(400, message="Missing restaurant_id in query parameters.")

            category = FoodCategory.query.filter_by(
                id=category_id,
                is_deleted=False,
                restaurant_id=restaurant_id
            ).first()

            if not category:
                abort(404, message="Food Category not found.")
            return category

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching food categories: {str(e)}")


@blp.route('/items')
class FoodItemsApi(MethodView):
    @jwt_required()
    @blp.arguments(FoodItemSchema(many=True))
    def post(self, data):
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can define food items.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            # Get existing items for duplicate checking
            existing_items = {
                item.name.lower(): item
                for item in FoodItem.query.join(FoodCategory)
                .filter(
                    FoodCategory.restaurant_id == user.restaurant_id,
                    FoodItem.is_deleted == False
                ).all()
            }

            new_items = []
            for item_data in data:
                # Check for duplicate (case-insensitive)
                if item_data["name"].strip().lower() in existing_items:
                    continue

                # Verify category belongs to restaurant
                category = FoodCategory.query.filter_by(
                    id=item_data["food_category_id"],
                    restaurant_id=user.restaurant_id,
                    is_deleted=False
                ).first_or_404()

                # Verify offering periods belong to restaurant
                offering_periods = FoodOfferingPeriod.query.filter(
                    FoodOfferingPeriod.id.in_(
                        item_data["offering_period_ids"]),
                    FoodOfferingPeriod.restaurant_id == user.restaurant_id,
                    FoodOfferingPeriod.is_deleted == False
                ).all()

                if len(offering_periods) != len(item_data["offering_period_ids"]):
                    abort(400, message="Invalid offering period IDs")

                new_item = FoodItem(
                    name=item_data["name"].strip(),
                    description=item_data.get("description"),
                    base_price=item_data.get("base_price"),
                    is_available=item_data.get("is_available", True),
                    has_variants=item_data.get("has_variants", False),
                    food_category_id=item_data["food_category_id"]
                )

                # Add relationships
                new_item.offering_periods = offering_periods

                # Add dietary types if provided
                if "dietary_type_ids" in item_data:
                    dietary_types = DietaryType.query.filter(
                        DietaryType.id.in_(item_data["dietary_type_ids"]),
                        DietaryType.restaurant_id == user.restaurant_id,
                        DietaryType.is_deleted == False
                    ).all()

                    if len(dietary_types) != len(item_data["dietary_type_ids"]):
                        abort(400, message="Invalid dietary type IDs")

                    new_item.dietary_types = dietary_types

                new_items.append(new_item)
                existing_items[item_data["name"].strip().lower()] = new_item

            if new_items:
                db.session.add_all(new_items)
                db.session.commit()

            return {"message": f"{len(new_items)} food items added."}, 201

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, f"Error creating food items: {str(e)}")

    def get(self):
        """Public: Get all food items for a given restaurant ID (with categories, serving times, dietary types, and variants)."""
        try:
            restaurant_id = request.args.get("restaurant_id", type=int)
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            if not restaurant_id:
                abort(400, message="Missing restaurant_id in query parameters.")

            food_items = (
                db.session.query(FoodItem)
                .join(FoodCategory)
                .filter(
                    FoodItem.is_deleted == False,
                    FoodCategory.restaurant_id == restaurant_id,
                    FoodCategory.is_deleted == False
                )
                .options(
                    joinedload(FoodItem.category),
                    joinedload(FoodItem.offering_periods),
                    joinedload(FoodItem.dietary_types),
                    joinedload(FoodItem.variants)
                )
                .paginate(page=page, per_page=per_page)
            )

            result = []
            for item in food_items.items:
                result.append({
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "base_price": item.base_price,
                    "is_available": item.is_available,
                    "has_variants": item.has_variants,
                    "category": {
                        "id": item.category.id,
                        "name": item.category.name
                    } if item.category else None,
                    "offering_periods": [
                        {
                            "id": op.id,
                            "name": op.name,
                            "start_time": str(op.start_time),
                            "end_time": str(op.end_time)
                        }
                        for op in item.offering_periods if not op.is_deleted
                    ],
                    "dietary_types": [
                        {
                            "id": dt.id,
                            "name": dt.name
                        }
                        for dt in item.dietary_types if not dt.is_deleted
                    ],
                    "variants": [
                        {
                            "id": v.id,
                            "name": v.name,
                            "price": v.price,
                            "description": v.description
                        }
                        for v in item.variants
                    ]
                })

            return {
                "items": result,
                "total": food_items.total,
                "pages": food_items.pages,
                "current_page": food_items.page
            }, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching food items: {str(e)}")


@blp.route("/items/<int:food_item_id>")
class ModifyFoodItem(MethodView):
    @jwt_required()
    @blp.arguments(FoodItemSchema(partial=True))  # Allow partial updates
    def patch(self, data, food_item_id):
        """Partially update food item (excluding variants)."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can update food items.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            food_item = db.session.query(FoodItem).join(FoodCategory).filter(
                FoodItem.id == food_item_id,
                FoodItem.is_deleted == False,
                FoodCategory.restaurant_id == user.restaurant_id,
                FoodCategory.is_deleted == False
            ).first()

            if not food_item:
                abort(404, message="Food item not found or unauthorized.")

            if "variants" in data:
                abort(400, message="Variants cannot be updated here.")

            if "name" in data:
                food_item.name = data["name"].strip()
            if "description" in data:
                food_item.description = data["description"]
            if "base_price" in data:
                food_item.base_price = data["base_price"]
            if "is_available" in data:
                food_item.is_available = data["is_available"]

            if "has_variants" in data:
                if food_item.has_variants and not data["has_variants"]:
                    # From True → False, delete all variants
                    food_item.variants.clear()
                food_item.has_variants = data["has_variants"]

            if "offering_period_ids" in data:
                offering_periods = FoodOfferingPeriod.query.filter(
                    FoodOfferingPeriod.id.in_(data["offering_period_ids"]),
                    FoodOfferingPeriod.is_deleted == False,
                    FoodOfferingPeriod.restaurant_id == user.restaurant_id
                ).all()
                if len(offering_periods) != len(data["offering_period_ids"]):
                    abort(400, message="Invalid offering period IDs.")
                food_item.offering_periods = offering_periods

            if "dietary_type_ids" in data:
                dietary_types = DietaryType.query.filter(
                    DietaryType.id.in_(data["dietary_type_ids"]),
                    DietaryType.is_deleted == False,
                    DietaryType.restaurant_id == user.restaurant_id
                ).all()
                if len(dietary_types) != len(data["dietary_type_ids"]):
                    abort(400, message="Invalid dietary type IDs.")
                food_item.dietary_types = dietary_types

            db.session.commit()
            return {"message": "Food item updated successfully."}, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            db.session.rollback()
            abort(500, message=str(e))

    @jwt_required()
    def delete(self, food_item_id):
        """Soft delete a food item and its variants."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can delete food items.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            food_item = db.session.query(FoodItem).join(FoodCategory).filter(
                FoodItem.id == food_item_id,
                FoodItem.is_deleted == False,
                FoodCategory.restaurant_id == user.restaurant_id,
                FoodCategory.is_deleted == False
            ).first()

            if not food_item:
                abort(404, message="Food item not found or unauthorized.")

            food_item.is_deleted = True
            food_item.variants.clear()  # To ensure cascade delete-orphan works
            db.session.commit()
            return {"message": f"{food_item.name} deleted successfully."}, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            db.session.rollback()
            abort(500, message=str(e))

    def get(self, food_item_id):
        """Public: Get a food item for a given restaurant ID (with categories, serving times, dietary types, and variants)."""
        try:
            restaurant_id = request.args.get("restaurant_id", type=int)

            if not restaurant_id:
                abort(400, message="Missing restaurant_id in query parameters.")

            item = (
                db.session.query(FoodItem)
                .join(FoodCategory)
                .filter(
                    FoodItem.is_deleted == False,
                    FoodCategory.restaurant_id == restaurant_id,
                    FoodCategory.is_deleted == False,
                    FoodItem.id == food_item_id
                )
                .options(
                    joinedload(FoodItem.category),
                    joinedload(FoodItem.offering_periods),
                    joinedload(FoodItem.dietary_types),
                    joinedload(FoodItem.variants)
                )
                .first()
            )

            if not item:
                abort(404, message="Food item not found")

            result = {}
            result["data"] = ({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "base_price": item.base_price,
                "is_available": item.is_available,
                "has_variants": item.has_variants,
                "category": {
                    "id": item.category.id,
                    "name": item.category.name
                } if item.category else None,
                "offering_periods": [
                    {
                        "id": op.id,
                        "name": op.name,
                        "start_time": str(op.start_time),
                        "end_time": str(op.end_time)
                    }
                    for op in item.offering_periods if not op.is_deleted
                ],
                "dietary_types": [
                    {
                        "id": dt.id,
                        "name": dt.name
                    }
                    for dt in item.dietary_types if not dt.is_deleted
                ],
                "variants": [
                    {
                        "id": v.id,
                        "name": v.name,
                        "price": v.price,
                        "description": v.description
                    }
                    for v in item.variants
                ]
            })

            result["message"] = "food Item fetched successfully"
            return result, 200

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching food items: {str(e)}")


@blp.route("/items/<int:food_item_id>/variants")
class AddFoodItemVariants(MethodView):
    @jwt_required()
    # Expecting a list of variants
    @blp.arguments(FoodItemVariantSchema(many=True))
    def post(self, data, food_item_id):
        """Add variants to a particular food item."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can add variants.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            food_item = FoodItem.query.filter_by(
                id=food_item_id, is_deleted=False).first()
            if not food_item:
                abort(404, message="Food item not found.")

            if food_item.has_variants is False:
                abort(400, message="Thisn Food item doesn't support variants.")

            # Retrieve the restaurant_id from the food item's category
            restaurant_id = food_item.category.restaurant_id

            if restaurant_id != user.restaurant_id:
                abort(
                    403, message="You can only modify food items belonging to your restaurant.")

            # Check for duplicate variant names within the input data
            variant_names = [variant["name"].strip() for variant in data]
            if len(variant_names) != len(set(variant_names)):
                abort(
                    400, message="Duplicate variant names are not allowed in the input data.")

            # Check for duplicate variant names within the existing variants of the food item
            existing_variant_names = [
                variant.name for variant in food_item.variants]
            for variant_data in data:
                variant_name = variant_data["name"].strip()

                if variant_name in existing_variant_names:
                    abort(
                        400, message=f"Variant '{variant_name}' already exists for this food item.")

                # Append the variant if no duplicates
                variant = FoodItemVariant(
                    name=variant_name,
                    price=variant_data["price"],
                    description=variant_data.get("description")
                )
                food_item.variants.append(variant)

            db.session.commit()

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Error adding variants: {str(e)}")

        return {"message": "Variants added successfully."}, 201

    @blp.response(200)
    def get(self, food_item_id):
        """Get all variants of a specific food item."""
        try:
            restaurant_id = request.args.get("restaurant_id", type=int)
            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            if not restaurant_id:
                abort(400, message="Missing restaurant_id in query parameters.")

            food_item = FoodItem.query.options(joinedload(FoodItem.variants)).join(FoodCategory).filter(
                FoodItem.id == food_item_id,
                FoodItem.is_deleted == False,
                FoodCategory.restaurant_id == restaurant_id,
                FoodCategory.is_deleted == False
            ).first()

            if not food_item:
                abort(404, message="Food item not found or unauthorized access.")

            # Get paginated variants
            variants_query = FoodItemVariant.query.filter_by(
                food_item_id=food_item_id,
                is_deleted=False
            )
            variants = variants_query.paginate(page=page, per_page=per_page)

            variants_list = [
                {
                    "id": variant.id,
                    "name": variant.name,
                    "price": variant.price,
                    "description": variant.description
                }
                for variant in variants.items
            ]

            return {
                "items": variants_list,
                "total": variants.total,
                "pages": variants.pages,
                "current_page": variants.page
            }

        except HTTPException:
            raise  # Let abort() exceptions propagate

        except Exception as e:
            abort(500, message=f"Error fetching variants: {str(e)}")


@blp.route("/items/<int:food_item_id>/variants/<int:variant_id>")
class ManageFoodItemVariant(MethodView):
    def get(self, food_item_id, variant_id):
        """Fetch a specific variant of a food item."""
        try:
            restaurant_id = request.args.get("restaurant_id", type=int)
            if not restaurant_id:
                abort(400, message="Missing restaurant_id in query parameters.")

            food_item = db.session.query(FoodItem).join(FoodCategory).filter(
                FoodItem.id == food_item_id,
                FoodItem.is_deleted == False,
                FoodCategory.restaurant_id == restaurant_id,
                FoodCategory.is_deleted == False
            ).first()

            if not food_item:
                abort(404, message="Food item not found or unauthorized.")

            variant = FoodItemVariant.query.filter_by(
                id=variant_id, food_item_id=food_item_id, is_deleted=False
            ).first()

            if not variant:
                abort(404, message="Variant not found.")

            return {
                "id": variant.id,
                "name": variant.name,
                "price": variant.price,
                "description": variant.description,
            }

        except HTTPException:
            raise
        except Exception as e:
            abort(500, message=f"Error fetching variant: {str(e)}")

    @jwt_required()
    # Allow partial updates
    @blp.arguments(FoodItemVariantSchema(partial=True))
    def patch(self, data, food_item_id, variant_id):
        """Update a specific variant of a food item."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can update variants.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            food_item = FoodItem.query.filter_by(
                id=food_item_id, is_deleted=False).first()
            if not food_item:
                abort(404, message="Food item not found.")

            if food_item.category.restaurant_id != user.restaurant_id:
                abort(403, message="You can only modify items in your own restaurant.")

            variant = FoodItemVariant.query.filter_by(
                id=variant_id, food_item_id=food_item_id, is_deleted=False
            ).first()

            if not variant:
                abort(404, message="Variant not found.")

            if "name" in data:
                variant.name = data["name"].strip()
            if "price" in data:
                variant.price = data["price"]
            if "description" in data:
                variant.description = data["description"]

            db.session.commit()
            return {"message": "Variant updated successfully."}

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Error updating variant: {str(e)}")

    @jwt_required()
    def delete(self, food_item_id, variant_id):
        """Remove a variant from a food item."""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()

            if claims.get("role") != "staff":
                abort(403, message="Only staff can remove variants.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            food_item = FoodItem.query.filter_by(
                id=food_item_id, is_deleted=False).first()
            if not food_item:
                abort(404, message="Food item not found.")

            if food_item.category.restaurant_id != user.restaurant_id:
                abort(403, message="You can only modify items in your own restaurant.")

            variant = FoodItemVariant.query.filter_by(
                id=variant_id, food_item_id=food_item_id, is_deleted=False
            ).first()

            if not variant:
                abort(404, message="Variant not found.")

            db.session.delete(variant)
            db.session.commit()
            return {"message": "Variant removed successfully."}, 200

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, message=f"Error removing variant: {str(e)}")


@blp.route("/restaurant/<int:restaurant_id>/food-categories")
class FoodCategoryBulkAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodCategorySchema(many=True))
    @blp.response(201, FoodCategorySchema(many=True))
    def post(self, categories_data, restaurant_id):
        """Create multiple food categories with duplicate checking"""
        # Verify restaurant exists
        restaurant = Restaurant.query.get_or_404(restaurant_id)

        # Get existing category names for this restaurant
        existing_categories = {
            cat.name.lower(): cat
            for cat in FoodCategory.query.filter_by(restaurant_id=restaurant_id).all()
        }

        new_categories = []
        for category in categories_data:
            # Check for duplicates (case-insensitive)
            if category["name"].lower() in existing_categories:
                continue

            new_category = FoodCategory(
                name=category["name"],
                description=category.get("description"),
                restaurant_id=restaurant_id
            )
            new_categories.append(new_category)
            existing_categories[category["name"].lower()] = new_category

        if new_categories:
            db.session.add_all(new_categories)
            db.session.commit()

        return new_categories


@blp.route("/restaurant/<int:restaurant_id>/dietary-types")
class DietaryTypeBulkAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodDietaryTypeSchema(many=True))
    @blp.response(201, FoodDietaryTypeSchema(many=True))
    def post(self, dietary_types_data, restaurant_id):
        """Create multiple dietary types with duplicate checking"""
        # Verify restaurant exists
        restaurant = Restaurant.query.get_or_404(restaurant_id)

        # Get existing dietary type names for this restaurant
        existing_types = {
            dt.name.lower(): dt
            for dt in DietaryType.query.filter_by(restaurant_id=restaurant_id).all()
        }

        new_types = []
        for dietary_type in dietary_types_data:
            # Check for duplicates (case-insensitive)
            if dietary_type["name"].lower() in existing_types:
                continue

            new_type = DietaryType(
                name=dietary_type["name"],
                description=dietary_type.get("description"),
                restaurant_id=restaurant_id
            )
            new_types.append(new_type)
            existing_types[dietary_type["name"].lower()] = new_type

        if new_types:
            db.session.add_all(new_types)
            db.session.commit()

        return new_types


@blp.route("/restaurant/<int:restaurant_id>/food-items")
class FoodItemBulkAPI(MethodView):
    @jwt_required()
    @blp.arguments(FoodItemSchema(many=True))
    @blp.response(201, FoodItemSchema(many=True))
    def post(self, food_items_data, restaurant_id):
        """Create multiple food items with duplicate checking"""
        # Verify restaurant exists
        restaurant = Restaurant.query.get_or_404(restaurant_id)

        # Get existing food item names for this restaurant
        existing_items = {
            item.name.lower(): item
            for item in FoodItem.query.join(FoodCategory)
            .filter(FoodCategory.restaurant_id == restaurant_id).all()
        }

        new_items = []
        for item in food_items_data:
            # Check for duplicates (case-insensitive)
            if item["name"].lower() in existing_items:
                continue

            # Verify category belongs to restaurant
            category = FoodCategory.query.filter_by(
                id=item["food_category_id"],
                restaurant_id=restaurant_id
            ).first_or_404()

            # Verify offering periods belong to restaurant
            offering_periods = FoodOfferingPeriod.query.filter(
                FoodOfferingPeriod.id.in_(item["offering_period_ids"]),
                FoodOfferingPeriod.restaurant_id == restaurant_id
            ).all()

            if len(offering_periods) != len(item["offering_period_ids"]):
                abort(400, message="Invalid offering period IDs")

            new_item = FoodItem(
                name=item["name"],
                description=item.get("description"),
                base_price=item.get("base_price"),
                is_available=item.get("is_available", True),
                has_variants=item.get("has_variants", False),
                food_category_id=item["food_category_id"]
            )

            # Add relationships
            new_item.offering_periods = offering_periods

            # Add dietary types if provided
            if "dietary_type_ids" in item:
                dietary_types = DietaryType.query.filter(
                    DietaryType.id.in_(item["dietary_type_ids"]),
                    DietaryType.restaurant_id == restaurant_id
                ).all()

                if len(dietary_types) != len(item["dietary_type_ids"]):
                    abort(400, message="Invalid dietary type IDs")

                new_item.dietary_types = dietary_types

            new_items.append(new_item)
            existing_items[item["name"].lower()] = new_item

        if new_items:
            db.session.add_all(new_items)
            db.session.commit()

        return new_items
