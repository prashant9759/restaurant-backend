from flask_smorest import Blueprint, abort
from app import db
from app.models import (
    Restaurant, FoodItem,
    FoodItemVariant,
    FoodOfferingPeriod,
    Booking,
    ReservationFoodOrder,
    OrderItem,
    FoodItemStock,
    User
)
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.schemas import (
    FoodOrderUpdateSchema
)
from datetime import datetime
import pytz
from sqlalchemy.orm import selectinload

blp = Blueprint('food_serving', __name__, url_prefix="/api/foods-servings")


@blp.route("/restaurants/<int:restaurant_id>/available-food-items", methods=["GET"])
def get_available_food_items(restaurant_id):
    try:
        restaurant = Restaurant.query.get(restaurant_id)
        if not restaurant:
            return {"error": "Restaurant not found"}, 404

        try:
            restaurant_tz = pytz.timezone(restaurant.timezone)
        except Exception:
            return {"error": "Invalid restaurant timezone"}, 500

        now_utc = datetime.utcnow()
        local_time = now_utc.astimezone(restaurant_tz).time()

        offering_period = FoodOfferingPeriod.query.filter(
            FoodOfferingPeriod.restaurant_id == restaurant.id,
            FoodOfferingPeriod.start_time <= local_time,
            FoodOfferingPeriod.end_time > local_time,
            FoodOfferingPeriod.is_deleted == False
        ).first()

        if not offering_period:
            return {
                "timestamp": now_utc.isoformat(),
                "restaurant_time": local_time.strftime("%H:%M:%S"),
                "offering_period": None,
                "available_items_by_category": []
            }

        # Filter food items for the current offering period
        food_items = FoodItem.query.options(
            selectinload(FoodItem.category),
            selectinload(FoodItem.dietary_types),
            selectinload(FoodItem.variants)
        ).filter(
            FoodItem.is_deleted == False,
            FoodItem.is_available == True,
            FoodItem.offering_periods.any(id=offering_period.id)
        ).all()

        # Group by category_id
        category_map = {}
        for item in food_items:
            cat = item.category
            if cat.id not in category_map:
                category_map[cat.id] = {
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "category_description": cat.description,
                    "items": []
                }
            category_map[cat.id]["items"].append({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "base_price": item.base_price,
                "dietary_types": [dt.name for dt in item.dietary_types if not dt.is_deleted],
                "variants": [
                    {
                        "id": variant.id,
                        "name": variant.name,
                        "price": variant.price,
                        "description": variant.description
                    }
                    for variant in item.variants if not variant.is_deleted
                ]
            })

        return {
            "timestamp": now_utc.isoformat(),
            "restaurant_time": local_time.strftime("%H:%M:%S"),
            "offering_period": offering_period.name,
            "available_items_by_category": list(category_map.values())
        }

    except Exception as e:
        return {"error": "Internal server error", "details": str(e)}, 500


@blp.route("/reservations/<int:booking_id>/food-order", methods=["PUT"])
@jwt_required()
@blp.arguments(FoodOrderUpdateSchema)
def create_or_update_food_order(data, booking_id):
    try:
        # Check if user is staff
        user_id = get_jwt_identity()
        claims = get_jwt()
        if claims.get("role") != "staff":
            abort(403, message="Only staff can create or update food orders.")

        # Get staff user
        user = User.query.filter_by(id=user_id, is_deleted=False).first()
        if not user:
            abort(404, message="Staff not found.")

        item_entries = data.get("items", [])

        reservation = Booking.query.get(booking_id)
        if not reservation:
            return {"error": f"Reservation with id {booking_id} not found"}, 404

        # Check if staff belongs to the same restaurant as the reservation
        if reservation.restaurant_id != user.restaurant_id:
            abort(403, message="You can only manage orders for your own restaurant.")

        if reservation.status != "active":
            return {"error": "Reservation is not active"}, 400

        # Retrieve or create order
        order = reservation.food_order
        if not order:
            order = ReservationFoodOrder(reservation_id=booking_id)
            db.session.add(order)

        if order.is_finalized:
            return {"error": "Order is finalized and cannot be modified"}, 400

        # Get available food items during reservation start time
        available_food_ids = get_available_food_item_ids(
            reservation.start_time, reservation.restaurant_id)

        # Build existing item map
        existing_items = {(item.food_item_id, item.variant_id)
                           : item for item in order.items}
        updated_keys = set()

        for entry in item_entries:
            fid = entry["food_item_id"]
            vid = entry.get("variant_id")
            qty = entry["quantity"]
            key = (fid, vid)
            updated_keys.add(key)

            if fid not in available_food_ids:
                return {"error": f"Food item {fid} is not available at reservation time"}, 400

            food_item = FoodItem.query.get(fid)
            if not food_item:
                return {"error": f"Food item {fid} not found"}, 404

            # Validate that variant_id is provided when food item has variants
            if food_item.has_variants and not vid:
                return {"error": f"Food item {fid} has variants. Please specify a variant_id."}, 400

            variant = None
            price = food_item.base_price
            if vid:
                variant = FoodItemVariant.query.get(vid)
                if not variant or variant.food_item_id != fid:
                    return {"error": f"Invalid variant {vid} for food item {fid}"}, 400
                price = variant.price

            # Fetch or check stock entry
            stock_entry = FoodItemStock.query.filter_by(
                food_item_id=fid, variant_id=vid).first()
            if not stock_entry:
                return {"error": f"No stock entry for food item {fid} variant {vid}"}, 404

            if key in existing_items:
                # Existing item - compute net change
                previous_qty = existing_items[key].quantity
                net_change = qty - previous_qty

                if net_change > 0 and net_change > stock_entry.current_stock:
                    return {"error": f"Insufficient stock for item {fid} variant {vid}"}, 400

                stock_entry.current_stock -= net_change
                existing_items[key].quantity = qty
            else:
                # New item
                if qty > stock_entry.current_stock:
                    return {"error": f"Insufficient stock for item {fid} variant {vid}"}, 400
                stock_entry.current_stock -= qty

                new_item = OrderItem(
                    food_item_id=fid,
                    variant_id=vid,
                    quantity=qty,
                    unit_price=price
                )
                order.items.append(new_item)

        # Handle removals
        for key, item in existing_items.items():
            if key not in updated_keys:
                stock_entry = FoodItemStock.query.filter_by(
                    food_item_id=item.food_item_id,
                    variant_id=item.variant_id
                ).first()
                if stock_entry:
                    stock_entry.current_stock += item.quantity
                db.session.delete(item)

        db.session.commit()
        return {"message": "Order created/updated", "order_id": order.id}, 200

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}, 500


def get_available_food_item_ids(start_time, restaurant_id):
    periods = FoodOfferingPeriod.query.filter(
        FoodOfferingPeriod.restaurant_id == restaurant_id,
        FoodOfferingPeriod.start_time <= start_time,
        FoodOfferingPeriod.end_time > start_time
    ).all()

    food_ids = set()
    for period in periods:
        food_ids.update([f.id for f in period.food_items])
    return food_ids









