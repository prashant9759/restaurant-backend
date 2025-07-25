from flask_smorest import Blueprint, abort
from flask.views import MethodView
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    get_jwt
)

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload
from flask import request


from app.models import (
    Restaurant,
    RestaurantPolicy,
    RestaurantOperatingHours,
    Feature,
    Speciality
)
from app import db
from app.schemas import (
    RestaurantSchema,
    RestaurantPolicySchema,
    UpdateFeatureSpecialitySchema,
    RestaurantOperatingHoursSchema
)
from app.services.helper import *

blp = Blueprint("Restaurants", __name__, description="Operations on Restaurants",
                url_prefix="/api/admins/restaurants")


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
    restaurant = Restaurant.query.filter(
        Restaurant.id == restaurant_id,
        Restaurant.is_deleted == False
    ).first_or_404()

    if str(restaurant.admin_id) != admin_id:
        abort(403, message="You do not have permission to modify this restaurant.")

    # Extract add/remove lists
    items_to_add = set(data.get("add", []))
    items_to_remove = set(data.get("remove", []))

    if not items_to_add and not items_to_remove:
        abort(400, message="Nothing to update.")

    # Get current items
    current_items = {getattr(i, "name")
                     for i in getattr(restaurant, item_name)}

    # Validate removals
    invalid_removals = items_to_remove - current_items
    if invalid_removals:
        abort(
            400, message=f"Cannot remove {item_name} that are not assigned to the restaurant: {', '.join(invalid_removals)}")

    # Validate additions
    invalid_additions = items_to_add & current_items
    if invalid_additions:
        abort(
            400, message=f"Cannot add {item_name} that are already assigned to the restaurant: {', '.join(invalid_additions)}")

    # Fetch valid items from DB
    valid_items = Model.query.filter(
        Model.name.in_(items_to_add | items_to_remove)).all()
    valid_item_names = {i.name for i in valid_items}

    # Identify invalid items
    invalid_items = (items_to_add | items_to_remove) - valid_item_names
    if invalid_items:
        abort(
            400, message=f"Invalid {item_name} provided: {', '.join(invalid_items)}")

    # Convert valid items into a dictionary for quick lookup
    item_map = {i.name: i for i in valid_items}

    # Add new items
    for name in items_to_add:
        getattr(restaurant, item_name).append(item_map[name])

    # Remove items
    setattr(restaurant, item_name, [i for i in getattr(
        restaurant, item_name) if i.name not in items_to_remove])

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


@blp.route("/")
class AdminList(MethodView):

    @jwt_required()
    @blp.arguments(RestaurantSchema)
    def post(self, data):
        """Create a new restaurant with policy, cuisines, food preferences, and working hours."""
        check_admin_role()

        if data.get("phone"):
            phone_exists = db.session.query(
                db.exists().where(
                    Restaurant.phone == data["phone"],
                    Restaurant.is_deleted == False
                )
            ).scalar()
            

            if phone_exists:
                abort(
                    400, message="Phone number is already taken by another restaurant.")

        admin_id = get_jwt_identity()

        # Extract and create specialities
        speciality_names = data.pop("specialities", [])
        speciality_instances = [Speciality(name=name)
                                for name in speciality_names]

        # Extract and create features
        feature_names = data.pop("features", [])
        feature_instances = [Feature(name=name) for name in feature_names]

        # Extract and process policy
        policy_data = data.pop("policy", None)
        if not policy_data:
            abort(400, message="Policy information is required.")

        # Extract and process operating hours
        operating_hours_data = data.pop("operating_hours", [])
        if not operating_hours_data or len(operating_hours_data) != 7:
            abort(400, message="Operating hours for all 7 days must be provided.")

        operating_hours_instances = []
        try:
            for entry in operating_hours_data:
                day_of_week = entry.get("day_of_week")
                opening_time = entry.get("opening_time")
                closing_time = entry.get("closing_time")

                if day_of_week is None or opening_time is None or closing_time is None:
                    abort(
                        400, message="Each operating hour entry must have day_of_week, opening_time, and closing_time.")

                operating_hours_instances.append(
                    RestaurantOperatingHours(
                        day_of_week=day_of_week,
                        opening_time=opening_time,
                        closing_time=closing_time
                    )
                )

            # Create Policy and Restaurant together
            policy = RestaurantPolicy(**policy_data)
            restaurant = Restaurant(
                admin_id=admin_id,
                policy=policy,
                **data,
                operating_hours=operating_hours_instances,  # Add working hours
                specialities=speciality_instances,  # Assign new specialities
                features=feature_instances  # Assign new features
            )

            db.session.add(restaurant)
            db.session.commit()

        except IntegrityError as e:
            db.session.rollback()
            abort(400, message=f"Integrity Error: {e.orig}")
        except SQLAlchemyError as e:
            db.session.rollback()
            abort(
                500, message="An error occurred while creating the restaurant and policy.")

        return {
            "restaurant": restaurant.to_dict(),
            "message": "Restaurant created successfully",
            "status": 201
        }, 201


@blp.route("/<int:restaurant_id>")
class RestaurantSelf(MethodView):
    @jwt_required()
    def get(self, restaurant_id):
        """Get a specific restaurant if it belongs to the current admin."""
        check_admin_role()
        admin_id = get_jwt_identity()
        restaurant = (
            Restaurant.query
            .filter_by(id=restaurant_id, is_deleted=False)
            .first_or_404(description="Restaurant not found or deleted.")
        )

        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to access this restaurant.")

        return {
            "restaurant": restaurant.to_dict(),
            "message": "Restaurant fetched successfully",
            "status": 200
        }, 200

    @jwt_required()
    @blp.arguments(RestaurantSchema(partial=True))
    def patch(self, update_data, restaurant_id):
        """Update general details of a restaurant (excluding cuisines, address, food_preferences and policy)."""
        check_admin_role()
        admin_id = get_jwt_identity()

        restaurant = (
            Restaurant.query
            .filter_by(id=restaurant_id, is_deleted=False)
            .first_or_404(description="Restaurant not found or deleted.")
        )

        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to modify this restaurant.")

        # Remove unwanted fields (cuisines, address, policy) before updating
        restricted_fields = {"policy","operating_hours"}
        filtered_data = {key: value for key, value in update_data.items(
        ) if key not in restricted_fields}

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

        restaurant = (
            Restaurant.query
            .filter_by(id=restaurant_id, is_deleted=False)
            .first_or_404(description="Restaurant not found or deleted.")
        )
        if str(restaurant.admin_id) != admin_id:
            abort(403, message="You do not have permission to delete this restaurant.")

        restaurant.soft_delete()
        return {"message": "Restaurant deleted succefully", "status": 204}, 204


@blp.route("/all")
class AllRestaurants(MethodView):
    @jwt_required()
    def get(self):
        """Get all restaurants managed by the current admin."""
        check_admin_role()
        admin_id = get_jwt_identity()
        print("here")
        # Fetch all restaurants belonging to this admin
        restaurants = Restaurant.query.filter_by(
            admin_id=admin_id, is_deleted=False).all()
        if not restaurants or len(restaurants) == 0:
            abort(404, message="No restaurant found for this admin")
        return {
            "data": [restaurant.to_dict() for restaurant in restaurants],
            "message": "Restaurants fetched successfully",
            "status": 200
        }, 200


@blp.route("/<int:restaurant_id>/policy")
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
            abort(
                403, message="You do not have permission to modify this restaurant policy.")

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



@blp.route("/<int:restaurant_id>/operating-hours")
class RestaurantOperatingHoursView(MethodView):

    @jwt_required()
    @blp.arguments(RestaurantOperatingHoursSchema(many=True))
    def put(self, hours_data, restaurant_id):
        check_admin_role()
        admin_id = get_jwt_identity()
        
        restaurant = db.session.query(Restaurant)\
            .options(joinedload(Restaurant.operating_hours))\
            .filter(Restaurant.id == restaurant_id,
                    Restaurant.is_deleted==False,
                    Restaurant.admin_id==admin_id
                )\
            .first()

        if not restaurant:
            abort(404, message="Restaurant not found.")

        existing_hours = {hour.day_of_week: hour for hour in restaurant.operating_hours}

        for entry in hours_data:
            day = entry["day_of_week"]
            opening_time = entry["opening_time"]
            closing_time = entry["closing_time"]

            if day in existing_hours:
                # Update existing entry
                existing = existing_hours[day]
                existing.opening_time = opening_time
                existing.closing_time = closing_time
            else:
                # Add new entry
                new_hour = RestaurantOperatingHours(
                    restaurant_id=restaurant.id,
                    day_of_week=day,
                    opening_time=opening_time,
                    closing_time=closing_time
                )
                db.session.add(new_hour)

        db.session.commit()

        return {
            "message": "Operating hours updated successfully.",
            "updated_hours": [hour.to_dict() for hour in restaurant.operating_hours]
        }, 200



@blp.route("/<int:restaurant_id>/update-features-specialities")
class UpdateFeaturesSpecialities(MethodView):
    @jwt_required()
    @blp.arguments(UpdateFeatureSpecialitySchema)
    def put(self, data, restaurant_id):
        """
        Update (Add/Remove) Features & Specialities for a Restaurant.
        - **Add**: Always create new features/specialities, even if they exist.
        - **Remove**: Pass IDs to remove specific features/specialities.
        """
        check_admin_role()
        admin_id = get_jwt_identity()
        restaurant = db.session.query(Restaurant)\
            .options(joinedload(Restaurant.features), joinedload(Restaurant.specialities))\
            .filter(Restaurant.id == restaurant_id, Restaurant.is_deleted == False,Restaurant.admin_id == admin_id )\
            .first()

        if not restaurant:
            abort(404, message="Restaurant not found")

        try:
            # Handle Features
            features_data = data.get("features", {})
            self.handle_features(restaurant, features_data)

            # Handle Specialities
            specialities_data = data.get("specialities", {})
            self.handle_specialities(restaurant, specialities_data)

            db.session.commit()
            return {"message": "Features and specialities updated successfully"}, 200

        except SQLAlchemyError as e:
            db.session.rollback()
            abort(500, message=str(e))

    def handle_features(self, restaurant, features_data):
        """Helper function to add/remove features."""
        if "add" in features_data:
            self.add_features(restaurant, features_data["add"])
        if "remove" in features_data:
            self.remove_features(restaurant, features_data["remove"])

    def handle_specialities(self, restaurant, specialities_data):
        """Helper function to add/remove specialities."""
        if "add" in specialities_data:
            self.add_specialities(restaurant, specialities_data["add"])
        if "remove" in specialities_data:
            self.remove_specialities(restaurant, specialities_data["remove"])

    def add_features(self, restaurant, feature_names):
        """Always create new features and link them to the restaurant."""
        new_features = [Feature(name=name) for name in feature_names]
        db.session.add_all(new_features)  # Batch insert for better performance
        restaurant.features.extend(new_features)

    def remove_features(self, restaurant, feature_ids):
        """Remove features by ID efficiently using a batch query."""
        features_to_remove = Feature.query.filter(
            Feature.id.in_(feature_ids)).all()
        for feature in features_to_remove:
            if feature in restaurant.features:
                restaurant.features.remove(feature)
            db.session.delete(feature)
                    

    def add_specialities(self, restaurant, speciality_names):
        """Always create new specialities and link them to the restaurant."""
        new_specialities = [Speciality(name=name) for name in speciality_names]
        db.session.add_all(new_specialities)  # Batch insert
        restaurant.specialities.extend(new_specialities)

    def remove_specialities(self, restaurant, speciality_ids):
        """Remove specialities by ID efficiently using a batch query."""
        specialities_to_remove = Speciality.query.filter(
            Speciality.id.in_(speciality_ids)).all()
        for speciality in specialities_to_remove:
            if speciality in restaurant.specialities:
                restaurant.specialities.remove(speciality)
            db.session.delete(speciality)




# Update Feature
@blp.route("/<int:restaurant_id>/features/<int:feature_id>", methods=["PATCH"])
@jwt_required()
def update_feature( restaurant_id , feature_id):
    check_admin_role()
    admin_id = get_jwt_identity()
    
    restaurant = db.session.query(Restaurant)\
        .filter(Restaurant.id == restaurant_id, Restaurant.is_deleted == False,Restaurant.admin_id == admin_id )\
        .first()

    if not restaurant:
        abort(404, message="Restaurant not found")
        
    data = request.get_json()
    new_name = data.get("name")
    
    if not new_name:
        return {"error": "Feature name is required"}, 400
    
    
    feature = db.session.query(Feature).join(restaurant_features).filter(
        Feature.id == feature_id, restaurant_features.c.restaurant_id == restaurant_id
    ).first()
    
    if not feature:
        return {"error": "Feature not found in this restaurant"}, 404
    
    feature.name = new_name
    try:
        db.session.commit()
        return {"message": "Feature updated successfully"},200
    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500



# Update Speciality
@blp.route("/<int:restaurant_id>/specialities/<int:speciality_id>", methods=["PATCH"])
@jwt_required()
def update_speciality( restaurant_id, speciality_id):
    check_admin_role()
    admin_id = get_jwt_identity()
    restaurant = db.session.query(Restaurant)\
        .filter(Restaurant.id == restaurant_id, Restaurant.is_deleted == False,Restaurant.admin_id == admin_id )\
        .first()

    if not restaurant:
        abort(404, message="Restaurant not found")
        
    data = request.get_json()
    new_name = data.get("name")
    
    if not new_name:
        return {"error": "Speciality name is required"}, 400
    
    
    speciality = db.session.query(Speciality).join(restaurant_specialities).filter(
        Speciality.id == speciality_id, restaurant_specialities.c.restaurant_id == restaurant_id
    ).first()
    
    if not speciality:
        return {"error": "Speciality not found in this restaurant"}, 404
    
    speciality.name = new_name
    try:
        db.session.commit()
        return {"message": "Speciality updated successfully"}
    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error"}, 500