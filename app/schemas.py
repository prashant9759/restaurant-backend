from marshmallow import (
    Schema, 
    fields, 
    validate, 
    validates, 
    ValidationError, 
    post_load, 
    validates_schema
)

from sqlalchemy import select
import re
from enum import Enum
from datetime import datetime



class Weekday(Enum):
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


# Mapping weekdays to numbers
WEEKDAYS = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6
}


class TableSchema(Schema):
    id = fields.Int(dump_only=True)
    table_type_id = fields.Int(required=True)
    table_number = fields.Str(required=True, validate=validate.Length(min=1))
    location_description = fields.Str(allow_none=True)
    is_available = fields.Bool(missing=True)
    capacity= fields.Int(required=True)


class TableTypeSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    minimum_capacity = fields.Int(required=True, validate=validate.Range(min=1))
    maximum_capacity = fields.Int(required=True, validate=validate.Range(min=1))
    description = fields.Str(validate=validate.Length(max=200))
    cover_image = fields.Str(validate=validate.Length(max=200))
    features = fields.List(fields.Str(), required=False)  # New features field (List of Strings)
    shape = fields.Str(required=True)

    @post_load
    def validate_table_type(self, data, **kwargs):
        if data.get("minimum_capacity", 0) > data.get("maximum_capacity", 10000000000):  # Fixed validation logic
            raise ValidationError("Minimum capacity must be smaller than Maximum capacity.")
        return data


        

class AdminSchema(Schema):
    id = fields.Int(dump_only=True)
    first_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    middle_name = fields.Str(required=False, validate=validate.Length(min=1, max=50))
    last_name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    email = fields.Email(required=True, validate=validate.Length(max=120))
    phone = fields.Str(
        required=False,
        validate=validate.Regexp(
            r"^\+\d{1,3}\d{4,14}$",  
            error="Invalid phone number. Must be in E.164 format (e.g., +14155552671)."
        )
    )
    # ✅ Added fields
    bio = fields.Str(required=False, validate=validate.Length(max=5000))  # Max 5000 characters for user bio
    profile_image = fields.Str(required=False, validate=validate.Length(max=255))  # Stores URL/path to profile image

    @validates("phone")
    def validate_phone_number(self, value):
        if not re.fullmatch(r"^\+\d{1,3}\d{4,14}$", value):
            raise ValidationError("Phone number must follow E.164 format.")
    password = fields.Str(
        required=True, 
        load_only=True, 
        validate=validate.Length(min=8, error="Password must be at least 8 characters")
    )
    confirm_password = fields.Str(
        required=True, 
        load_only=True
    )

    @validates_schema
    def validate_password_match(self, data, **kwargs):
        """Ensure password and confirm_password match."""
        if data.get("password") != data.get("confirm_password"):
            raise ValidationError({"confirm_password": "Passwords do not match."})


class AdminEmailVerificationSchema(Schema):
    email = fields.Email(required=True)
    verification_code = fields.String(required=True)
    
class UserEmailVerificationSchema(AdminEmailVerificationSchema):
    restaurant_id = fields.Int(required=True)
    role = fields.Str(
        required=True,
        validate=validate.OneOf(["user", "staff"]),
        error_messages={"validator_failed": "Role must be either 'user' or 'staff'."}
    )
    

class UserSchema(AdminSchema):
    restaurant_id = fields.Int(required=True)
    role = fields.Str(
        required=True,
        validate=validate.OneOf(["user", "staff"]),
        error_messages={"validator_failed": "Role must be either 'user' or 'staff'."}
    )



class RestaurantOperatingHoursSchema(Schema):
    """Handles opening and closing times for each day of the week."""
    day_of_week = fields.Str(
        required=True,
        validate=validate.OneOf([day.value for day in Weekday]),
        description="Day of the week (e.g., 'Monday')"
    )
    opening_time = fields.Time(required=True, format='%H:%M')
    closing_time = fields.Time(required=True, format='%H:%M')

    @validates("opening_time")
    def validate_opening_time(self, value):
        if not value:
            raise ValidationError("Opening time cannot be empty.")

    @validates("closing_time")
    def validate_closing_time(self, value):
        if not value:
            raise ValidationError("Closing time cannot be empty.")

    @validates_schema
    def validate_opening_closing(self, data, **kwargs):
        """Ensure closing time is after opening time."""
        if "opening_time" in data and "closing_time" in data:
            if data["closing_time"] <= data["opening_time"]:
                raise ValidationError("Closing time must be after opening time.")
            
    @post_load
    def convert_day_to_number(self, data, **kwargs):
        """Convert weekday name to number before saving."""
        data["day_of_week"] = WEEKDAYS[data["day_of_week"]]
        return data




class RestaurantPolicySchema(Schema):
    id = fields.Int(dump_only=True)

    max_party_size = fields.Int(required=True, validate=validate.Range(min=1))
    max_advance_days = fields.Int(required=True, validate=validate.Range(min=0))
    reservation_duration = fields.Int(required=True, validate=validate.Range(min=1))




class RestaurantSchema(Schema):
    """Main schema for restaurant details."""
    name = fields.String(required=True, validate=validate.Length(min=1))
    cover_image = fields.String(required=False)
    description = fields.String(required=False)
    features = fields.List(fields.Str(), required=False)  # List of feature strings
    specialities = fields.List(fields.Str(), required=False)  # List of specialty strings
    average_cost_level = fields.Int(required=True,validate=validate.Range(min=1))  
    phone = fields.Str(
        required=False,
        validate=validate.Regexp(
            r"^\+\d{1,3}\d{4,14}$",  
            error="Invalid phone number. Must be in E.164 format (e.g., +14155552671)."
        )
    )

    # Nested Fields
    address = fields.String(required=True)
    timezone = fields.String(required=True)
    policy = fields.Nested(RestaurantPolicySchema, required=True)
    operating_hours = fields.List(fields.Nested(RestaurantOperatingHoursSchema), required=True)

    @validates('cover_image')
    def validate_cover_image(self, value):
        if value and not value.startswith(('http://', 'https://')):
            raise ValidationError("Cover image URL must start with http:// or https://")



class BookingRequestSchema(Schema):
    guest_count = fields.Int(required=True, validate=validate.Range(min=1))
    date = fields.Date(required=True)
    start_time = fields.Str(
        required=True,
        validate=validate.Regexp(r"^(?:[01]\d|2[0-3]):[0-5]\d$", error="Invalid time format. Use HH:MM")
    )
    table_type_info = fields.List(
        fields.Integer(strict=True),
        required=False,
        validate=validate.Length(min=1)
    )
    customer_name = fields.Str(required=False)
    customer_phone = fields.Str(required=False)


class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True, load_only=True)
    new_password = fields.Str(
        required=True, 
        load_only=True, 
        validate=validate.Length(min=8, error="Password must be at least 8 characters")
    )
    confirm_new_password = fields.Str(required=True, load_only=True)

    @validates_schema
    def validate_password_match(self, data, **kwargs):
        """Ensure new password and confirm new password match."""
        if data.get("new_password") != data.get("confirm_new_password"):
            raise ValidationError({"confirm_new_password": "Passwords do not match."})



class RestaurantReviewSchema(Schema):
    id = fields.Int(dump_only=True)
    rating = fields.Float(
        required=True,
        validate=validate.Range(min=1.0, max=5.0, error="Rating must be between 1.0 and 5.0")
    )
    review = fields.Str(
        required=False,
        validate=validate.Length(max=5000, error="Review cannot exceed 5000 characters")
    )

    @validates("review")
    def validate_review(self, value):
        """Ensure review is not just empty spaces."""
        if value and value.strip() == "":
            raise ValidationError("Review cannot be empty or only spaces.")




class FeatureSpecialityActionSchema(Schema):
    add = fields.List(fields.String(), required=False)
    remove = fields.List(fields.Integer(), required=False)



class UpdateFeatureSpecialitySchema(Schema):
    features = fields.Nested(FeatureSpecialityActionSchema, required=False)
    specialities = fields.Nested(FeatureSpecialityActionSchema, required=False)



    
class AdminLoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)
    
class UserLoginSchema(AdminLoginSchema):
    restaurant_id = fields.Int(required=True)
    role = fields.Str(
        required=True,
        validate=validate.OneOf(["user", "staff"]),
        error_messages={"validator_failed": "Role must be either 'user' or 'staff'."}
    )
    


class FoodOfferingPeriodSchema(Schema):
    id = fields.Int(dump_only =True)
    name = fields.Str(required=True)
    start_time = fields.Str(required=True, example="08:00")
    end_time = fields.Str(required=True, example="11:30")

    @validates_schema
    def validate_times(self, data, **kwargs):
        try:
            start = datetime.strptime(data["start_time"], "%H:%M").time()
            end = datetime.strptime(data["end_time"], "%H:%M").time()
        except ValueError:
            raise ValidationError("Invalid time format. Use HH:MM.", field_name="start_time")

        if start >= end:
            raise ValidationError("Start time must be before end time.", field_name="start_time")



class FoodCategorySchema(Schema):
    id = fields.Int(dump_only =True)
    name = fields.Str(required=True)
    description = fields.Str(required=False)
    



class FoodDietaryTypeSchema(Schema):
    id = fields.Int(dump_only =True)
    name = fields.Str(required=True)
    description = fields.Str(required=False)



class FoodItemVariantSchema(Schema):
    id = fields.Int(dump_only =True)
    name = fields.Str(required=True)
    price = fields.Float(required=True)
    description = fields.Str(required=False)



class FoodItemSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    description = fields.Str(required=False)
    base_price = fields.Float(required=False)
    is_available = fields.Bool(missing=True)
    has_variants = fields.Bool(missing=False)
    food_category_id = fields.Int(required=True)

    offering_period_ids = fields.List(fields.Int(), required=True)
    dietary_type_ids = fields.List(fields.Int(), required=True)

    variants = fields.List(fields.Nested(FoodItemVariantSchema), required=False)




class FoodOrderItemSchema(Schema):
    food_item_id = fields.Integer(required=True)
    variant_id = fields.Integer(allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))

    @staticmethod
    def validate_variant(data):
        # Custom validator if needed later
        pass



class FoodOrderUpdateSchema(Schema):
    items = fields.List(fields.Nested(FoodOrderItemSchema), required=True, validate=validate.Length(min=1))




class FoodStockSchema(Schema):
    id = fields.Int(dump_only=True)
    food_item_id = fields.Int(required=True)
    variant_id = fields.Int(allow_none=True)
    current_stock = fields.Int(required=True, validate=validate.Range(min=0))
    threshold = fields.Int(required=True, validate=validate.Range(min=0))
    last_updated = fields.DateTime(dump_only=True)











































































