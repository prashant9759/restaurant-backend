from email import message
from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import (
        get_jwt_identity, 
        jwt_required, 
        get_jwt
    )

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import raiseload


from models import (
    Restaurant, 
    CuisineType,
    FoodPreferenceType,
    RestaurantPolicy,
    CityStateModel
)
from db import db
from schemas import  (
    RestaurantSchema , 
    RestaurantPolicySchema, 
    CuisineUpdateSchema, 
    FoodPreferenceUpdateSchema,
    AddressSchema
)
from services.helper import *

blp = Blueprint("Restaurants", __name__, description="Operations on Restaurants")

def check_admin_role():
    """Check if the JWT contains the 'admin' role."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        abort(403, message="Access forbidden: Admin role required.")


def handle_item_update(restaurant_id, data, item_name, Model):
    """
    Generic function to update restaurant items (cuisines or food_preferences).
    
    Parameters:
    - restaurant_id: ID of the restaurant
    - data: Dictionary containing "add" and "remove" lists
    - item_name: Name of the attribute in Restaurant model ("cuisines" or "food_preferences")
    - Model: SQLAlchemy model representing the item (CuisineType or FoodPreference)
    """
    check_admin_role()
    admin_id = get_jwt_identity()

    # Fetch restaurant and check permission
    restaurant = Restaurant.query.filter_by(id=restaurant_id).first_or_404()
    if str(restaurant.admin_id) != admin_id:
        abort(403, message="You do not have permission to modify this restaurant.")

    # Extract add/remove lists
    items_to_add = set(data.get("add", []))
    items_to_remove = set(data.get("remove", []))

    if not items_to_add and not items_to_remove:
        abort(400, message="Nothing to update.")

    # Get current items
    current_items = {getattr(i, "name") for i in getattr(restaurant, item_name)}

    # Validate removals
    invalid_removals = items_to_remove - current_items
    if invalid_removals:
        abort(400, message=f"Cannot remove {item_name} that are not assigned to the restaurant: {', '.join(invalid_removals)}")

    # Validate additions
    invalid_additions = items_to_add & current_items
    if invalid_additions:
        abort(400, message=f"Cannot add {item_name} that are already assigned to the restaurant: {', '.join(invalid_additions)}")

    # Fetch valid items from DB
    valid_items = Model.query.filter(Model.name.in_(items_to_add | items_to_remove)).all()
    valid_item_names = {i.name for i in valid_items}

    # Identify invalid items
    invalid_items = (items_to_add | items_to_remove) - valid_item_names
    if invalid_items:
        abort(400, message=f"Invalid {item_name} provided: {', '.join(invalid_items)}")

    # Convert valid items into a dictionary for quick lookup
    item_map = {i.name: i for i in valid_items}

    # Add new items
    for name in items_to_add:
        getattr(restaurant, item_name).append(item_map[name])

    # Remove items
    setattr(restaurant, item_name, [i for i in getattr(restaurant, item_name) if i.name not in items_to_remove])

    # Commit transaction
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message=f"Failed to update restaurant {item_name}.")

    return {
        "message": f"Restaurant {item_name} updated successfully.",
        item_name: [i.name for i in getattr(restaurant, item_name)],
    }, 200




@blp.route("/api/admins/restaurants")
class AdminList(MethodView):
    @jwt_required()
    @blp.arguments(RestaurantSchema)
    def post(self, data):
        """Create a new restaurant with policy and cuisines."""
        check_admin_role()
        admin_id = get_jwt_identity()
        exists = db.session.query(Restaurant.query.filter_by(admin_id=admin_id).exists()).scalar()
        if exists:
            return abort(400, message="Can't create more than 1 restaurant from the same admin id")

        address_field = manage_address_field(data)

        # Extract and process cuisines
        cuisine_names = data.pop("cuisines", [])
        cuisine_instances = CuisineType.query.filter(CuisineType.name.in_(cuisine_names)).all()

        if len(cuisine_instances) != len(cuisine_names):
            missing = set(cuisine_names) - {c.name for c in cuisine_instances}
            abort(400, message=f"Invalid cuisines provided: {', '.join(missing)}")
            
        # Extract and process cuisines
        food_preference_names = data.pop("food_preferences", [])
        food_preference_instances = FoodPreferenceType.query.filter(FoodPreferenceType.name.in_(food_preference_names)).all()

        if len(food_preference_instances) != len(food_preference_names):
            missing = set(food_preference_names) - {c.name for c in food_preference_instances}
            abort(400, message=f"Invalid foodPreferences provided: {', '.join(missing)}")

        # Extract and process policy
        policy_data = data.pop("policy", None)
        if not policy_data:
            abort(400, message="Policy information is required.")

        try:
            # Create Policy and Restaurant together (using relationship)
            policy = RestaurantPolicy(**policy_data)
            restaurant = Restaurant(
                admin_id=admin_id,
                policy=policy,  # Assign directly using relationship
                **data,
                **address_field,
                cuisines=cuisine_instances,
                food_preferences = food_preference_instances
            )

            db.session.add(restaurant)
            db.session.commit()

        except IntegrityError as e:
            db.session.rollback()
            abort(400, message=f"Integrity Error: {e.orig}")
        except SQLAlchemyError as e:
            db.session.rollback()
            print("Error:", e)
            abort(500, message="An error occurred while creating the restaurant and policy.")

        return {
            "restaurant": restaurant.to_dict(),
            "message": "Restaurant created successfully",
            "status": 201
        }, 201


@blp.route("/api/admins/restaurants/<int:restaurant_id>")
class RestaurantSelf(MethodView):
    @jwt_required()
    def get(self, restaurant_id):
        """Get a specific restaurant if it belongs to the current admin."""
        check_admin_role()
        admin_id = get_jwt_identity()
        restaurant = Restaurant.query.get(restaurant_id)
        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to access this restaurant.")

        return  {
            "restaurant": restaurant.to_dict(),
            "message": "Restaurant fetched successfully",
            "status": 200
        } , 200



    @jwt_required()
    @blp.arguments(RestaurantSchema(partial=True))
    def patch(self, update_data, restaurant_id):
        """Update general details of a restaurant (excluding cuisines, address, food_preferences and policy)."""
        check_admin_role()
        admin_id = get_jwt_identity()

        restaurant = db.session.query(Restaurant).filter_by(id=restaurant_id).first_or_404()


        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to modify this restaurant.")

        # Remove unwanted fields (cuisines, address, policy) before updating
        restricted_fields = {"cuisines", "address", "policy", "food_preferences"}
        filtered_data = {key: value for key, value in update_data.items() if key not in restricted_fields}

        if not filtered_data:
            abort(400, message="No valid fields provided for update.")

        # Update only the allowed fields
        for key, value in filtered_data.items():
            setattr(restaurant, key, value)

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="An error occurred while updating the restaurant.")

        return {
            "message": "Restaurant updated successfully.",
            "updated_fields": filtered_data
        }, 200


    @jwt_required()
    @blp.response(204)
    def delete(self, restaurant_id):
        """Delete the restaurant if it belongs to the admin."""
        check_admin_role()
        admin_id = get_jwt_identity()

        restaurant = Restaurant.query.get(restaurant_id)
        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to delete this restaurant.")

        return delete_logic(restaurant_id, Restaurant, "restaurant")


@blp.route("/api/admins/restaurants/all")
class AllRestaurants(MethodView):
    @jwt_required()
    def get(self):
        """Get all restaurants managed by the current admin."""
        check_admin_role()
        admin_id = get_jwt_identity()

        # Fetch all restaurants belonging to this admin
        restaurants = Restaurant.query.filter_by(admin_id=admin_id).all()
        if not restaurants or len(restaurants) ==0:
            abort(404, message="No restaurant found for this admin")
        return  {
            "data": [restaurant.to_dict() for restaurant in restaurants],
            "message": "Restaurants fetched successfully",
            "status": 200
        } , 200
   
   

@blp.route("/api/admins/restaurants/<int:restaurant_id>/policy")
class RestaurantPolicyResource(MethodView):

    @jwt_required()
    @blp.arguments(RestaurantPolicySchema(partial=True))
    def patch(self, policy_data, restaurant_id):
        """Partially update the restaurant policy."""
        check_admin_role()
        current_admin_id = get_jwt_identity()

        # Fetch admin_id & policy in a single query
        result = db.session.query(Restaurant.admin_id, RestaurantPolicy) \
            .join(RestaurantPolicy, Restaurant.policy_id == RestaurantPolicy.id) \
            .filter(Restaurant.id == restaurant_id).first()
        
        admin_id, policy = result if result else (None, None)

        if not policy:
            abort(404, message="Restaurant or policy not found.")

        # Verify restaurant ownership
        if str(admin_id) != current_admin_id:
            abort(403, message="You do not have permission to modify this restaurant policy.")

        # Update only provided fields
        for key, value in policy_data.items():
            setattr(policy, key, value)

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            abort(500, message="Failed to partially update restaurant policy.")

        return {
            "message": "Restaurant policy partially updated.",
            "policy": policy.to_dict()
        }, 200
        
        
@blp.route("/api/admins/restaurants/<int:restaurant_id>/cuisines")
class RestaurantCuisineResource(MethodView):

    @jwt_required()
    @blp.arguments(CuisineUpdateSchema)
    def patch(self, cuisine_data, restaurant_id):
        """Add or remove cuisines from a restaurant."""
        return handle_item_update(restaurant_id, cuisine_data,"cuisines",CuisineType)
    
@blp.route("/api/admins/restaurants/<int:restaurant_id>/food_preferences")
class RestaurantFoodPreferenceResource(MethodView):

    @jwt_required()
    @blp.arguments(FoodPreferenceUpdateSchema)
    def patch(self, food_preference_data, restaurant_id):
        """Add or remove food_preferences from a restaurant."""
        return handle_item_update(restaurant_id, food_preference_data,"food_preferences",FoodPreferenceType)
        

@blp.route("/api/admins/restaurants/<int:restaurant_id>/address")
class RestaurantAddressResource(MethodView):

    @jwt_required()
    @blp.arguments(AddressSchema(partial=True))
    def patch(self, data, restaurant_id):
        """Partially update the restaurant address."""
        check_admin_role()
        current_admin_id = get_jwt_identity()

        restaurant = Restaurant.query.get_or_404(restaurant_id)
        

        # Verify restaurant ownership
        if str(restaurant.admin_id) != current_admin_id:
            abort(403, message="You do not have permission to modify this restaurant policy.")
        return update_address(restaurant,data,"restaurant")
        