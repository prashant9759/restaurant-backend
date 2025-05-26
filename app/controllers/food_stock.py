from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import request
from app import db
from app.models import (
    User, FoodItem, FoodItemVariant, FoodItemStock
)
from app.schemas import FoodStockSchema
from sqlalchemy.orm import joinedload
from datetime import datetime
from werkzeug.exceptions import HTTPException

blp = Blueprint("food_stock_api", __name__, url_prefix="/api/food-stock")


@blp.route("/items")
class FoodStockList(MethodView):
    @jwt_required()
    def get(self):
        """Get all stock entries for a restaurant"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can view stock details.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            page = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 10, type=int)

            # Get all stock entries for food items in this restaurant
            stock_entries = (
                db.session.query(FoodItemStock)
                .join(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItem.category.has(restaurant_id=user.restaurant_id),
                    FoodItem.is_deleted == False
                )
                .options(
                    joinedload(FoodItemStock.food_item),
                    joinedload(FoodItemStock.variant)
                )
                .paginate(page=page, per_page=per_page)
            )

            result = []
            for entry in stock_entries.items:
                stock_data = {
                    "id": entry.id,
                    "food_item": {
                        "id": entry.food_item.id,
                        "name": entry.food_item.name
                    },
                    "current_stock": entry.current_stock,
                    "threshold": entry.threshold,
                    "last_updated": entry.last_updated.isoformat()
                }

                if entry.variant:
                    stock_data["variant"] = {
                        "id": entry.variant.id,
                        "name": entry.variant.name
                    }

                result.append(stock_data)

            return {
                "items": result,
                "total": stock_entries.total,
                "pages": stock_entries.pages,
                "current_page": stock_entries.page
            }, 200

        except Exception as e:
            abort(500, message=str(e))

    @jwt_required()
    @blp.arguments(FoodStockSchema)
    def post(self, data):
        """Create a new stock entry"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can manage stock.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            # Verify food item exists and belongs to restaurant
            food_item = (
                db.session.query(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItem.id == data["food_item_id"],
                    FoodItem.category.has(restaurant_id=user.restaurant_id),
                    FoodItem.is_deleted == False
                )
                .first()
            )

            if not food_item:
                abort(404, message="Food item not found or unauthorized.")

            # Validate that variant_id is provided when food item has variants
            if food_item.has_variants and not data.get("variant_id"):
                abort(
                    400, message="This food item has variants. Please specify a variant_id.")

            # If variant is specified, verify it exists and belongs to food item
            if data.get("variant_id"):
                variant = FoodItemVariant.query.filter_by(
                    id=data["variant_id"],
                    food_item_id=data["food_item_id"],
                    is_deleted=False
                ).first()
                if not variant:
                    abort(404, message="Variant not found or unauthorized.")

            # Check if stock entry already exists
            existing_entry = FoodItemStock.query.filter_by(
                food_item_id=data["food_item_id"],
                variant_id=data.get("variant_id")
            ).first()

            if existing_entry:
                abort(400, message="Stock entry already exists for this item/variant.")

            # Create new stock entry
            stock_entry = FoodItemStock(
                food_item_id=data["food_item_id"],
                variant_id=data.get("variant_id"),
                current_stock=data["current_stock"],
                threshold=data["threshold"]
            )

            db.session.add(stock_entry)
            db.session.commit()

            return {
                "message": "Stock entry created successfully",
                "stock_entry": FoodStockSchema().dump(stock_entry)
            }, 201

        except HTTPException:
            raise
        except Exception as e:
            db.session.rollback()
            abort(500, message=str(e))


@blp.route("/items/<int:stock_id>")
class FoodStockDetail(MethodView):
    @jwt_required()
    def get(self, stock_id):
        """Get a specific stock entry"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can view stock details.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            stock_entry = (
                db.session.query(FoodItemStock)
                .join(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItemStock.id == stock_id,
                    FoodItem.category.has(restaurant_id=user.restaurant_id)
                )
                .options(
                    joinedload(FoodItemStock.food_item),
                    joinedload(FoodItemStock.variant)
                )
                .first()
            )

            if not stock_entry:
                abort(404, message="Stock entry not found or unauthorized.")

            result = {
                "id": stock_entry.id,
                "food_item": {
                    "id": stock_entry.food_item.id,
                    "name": stock_entry.food_item.name
                },
                "current_stock": stock_entry.current_stock,
                "threshold": stock_entry.threshold,
                "last_updated": stock_entry.last_updated.isoformat()
            }

            if stock_entry.variant:
                result["variant"] = {
                    "id": stock_entry.variant.id,
                    "name": stock_entry.variant.name
                }

            return result, 200

        except Exception as e:
            abort(500, message=str(e))

    @jwt_required()
    @blp.arguments(FoodStockSchema(partial=True))
    def patch(self, data, stock_id):
        """Update a stock entry"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can manage stock.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            stock_entry = (
                db.session.query(FoodItemStock)
                .join(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItemStock.id == stock_id,
                    FoodItem.category.has(restaurant_id=user.restaurant_id)
                )
                .first()
            )

            if not stock_entry:
                abort(404, message="Stock entry not found or unauthorized.")

            # Update fields if provided
            if "current_stock" in data:
                stock_entry.current_stock = data["current_stock"]
            if "threshold" in data:
                stock_entry.threshold = data["threshold"]

            stock_entry.last_updated = datetime.utcnow()
            db.session.commit()

            return {
                "message": "Stock entry updated successfully",
                "stock_entry": FoodStockSchema().dump(stock_entry)
            }, 200

        except Exception as e:
            db.session.rollback()
            abort(500, message=str(e))

    @jwt_required()
    def delete(self, stock_id):
        """Delete a stock entry"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can manage stock.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            stock_entry = (
                db.session.query(FoodItemStock)
                .join(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItemStock.id == stock_id,
                    FoodItem.category.has(restaurant_id=user.restaurant_id)
                )
                .first()
            )

            if not stock_entry:
                abort(404, message="Stock entry not found or unauthorized.")

            db.session.delete(stock_entry)
            db.session.commit()

            return {"message": "Stock entry deleted successfully"}, 200

        except Exception as e:
            db.session.rollback()
            abort(500, message=str(e))


@blp.route("/items/<int:food_item_id>/stock")
class FoodItemStockDetail(MethodView):
    @jwt_required()
    def get(self, food_item_id):
        """Get stock information for a specific food item and variant"""
        try:
            user_id = get_jwt_identity()
            claims = get_jwt()
            if claims.get("role") != "staff":
                abort(403, message="Only staff can view stock details.")

            user = User.query.filter_by(id=user_id, is_deleted=False).first()
            if not user:
                abort(404, message="Staff not found.")

            # Get variant_id from query parameters
            variant_id = request.args.get("variant_id", type=int)

            # Verify food item exists and belongs to restaurant
            food_item = (
                db.session.query(FoodItem)
                .join(FoodItem.category)
                .filter(
                    FoodItem.id == food_item_id,
                    FoodItem.category.has(restaurant_id=user.restaurant_id),
                    FoodItem.is_deleted == False
                )
                .first()
            )

            if not food_item:
                abort(404, message="Food item not found or unauthorized.")

            # Validate that variant_id is provided when food item has variants
            if food_item.has_variants and not variant_id:
                abort(
                    400, message="This food item has variants. Please specify a variant_id.")

            # If variant is specified, verify it exists and belongs to food item
            if variant_id:
                variant = FoodItemVariant.query.filter_by(
                    id=variant_id,
                    food_item_id=food_item_id,
                    is_deleted=False
                ).first()
                if not variant:
                    abort(404, message="Variant not found or unauthorized.")

            # Get stock entry
            stock_entry = FoodItemStock.query.filter_by(
                food_item_id=food_item_id,
                variant_id=variant_id
            ).first()

            if not stock_entry:
                abort(
                    404, message="No stock entry found for this item/variant combination.")

            result = {
                "id": stock_entry.id,
                "food_item": {
                    "id": food_item.id,
                    "name": food_item.name,
                    "has_variants": food_item.has_variants
                },
                "current_stock": stock_entry.current_stock,
                "threshold": stock_entry.threshold,
                "last_updated": stock_entry.last_updated.isoformat()
            }

            if variant_id:
                result["variant"] = {
                    "id": variant.id,
                    "name": variant.name
                }

            return result, 200

        except HTTPException:
            raise
        except Exception as e:
            abort(500, message=str(e))






