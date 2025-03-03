from marshmallow import (
    Schema, 
    fields, 
    validate, 
    validates, 
    ValidationError, 
    post_load, 
    validates_schema
)

from models import (
    CuisineEnum, 
    Weekday, 
    WEEKDAY_BITMASK, 
    TableShape,
    FoodPreferenceEnum
)
from sqlalchemy import select



class TableSchema(Schema):
    id = fields.Int(dump_only=True)
    table_type_id = fields.Int(required=True)
    table_number = fields.Str(required=True, validate=validate.Length(min=1))
    location_description = fields.Str(allow_none=True)
    is_available = fields.Bool(missing=True)


class TableTypeSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=50))
    capacity = fields.Int(required=True, validate=validate.Range(min=1))
    price = fields.Float(required=True)
    description = fields.Str(validate=validate.Length(max=200))
    is_outdoor = fields.Bool(required=True)
    is_accessible = fields.Bool(missing=False)
    shape = fields.Str(
        required=True,
        validate=validate.OneOf([shape.value for shape in TableShape]),
        description="Shape of the table (e.g., 'Round', 'Square', 'Rectangle', 'Oval')"
    )

    @post_load
    def validate_table_type(self, data, **kwargs):
        if data.get("capacity", 1) < 1:
            raise ValidationError("Table capacity must be at least 1.")
        return data



class RestaurantPolicySchema(Schema):
    id = fields.Int(dump_only=True)

    # Accepts array of days in request body
    working_days = fields.List(
        fields.Str(validate=validate.OneOf([day.value for day in Weekday])),
        required=True,
        description="List of working days (e.g., ['Monday', 'Wednesday', 'Friday'])"
    )

    opening_time = fields.Time(required=True, format='%H:%M')
    closing_time = fields.Time(required=True, format='%H:%M')

    max_party_size = fields.Int(required=True, validate=validate.Range(min=1))
    max_advance_days = fields.Int(required=True, validate=validate.Range(min=0))
    reservation_duration = fields.Int(required=True, validate=validate.Range(min=1))
    cancellation_threshold = fields.Int(required=True, validate=validate.Range(min=1))

    @validates("working_days")
    def validate_days(self, value):
        if not value:
            raise ValidationError("At least one working day must be selected.")

    @post_load
    def convert_days_to_bitmask(self, data, **kwargs):
        """Convert list of days to bitmask before saving to DB."""
        if data.get("working_days"):
            day_bitmask = sum(WEEKDAY_BITMASK[day] for day in data["working_days"])
            data["working_days"] = day_bitmask
        return data




class BaseUserSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    email = fields.Email(required=True)
    phone = fields.Str()
    password = fields.Str(load_only=True, required=True)
    role = fields.Str(dump_only=True, default='user')
    created_at = fields.DateTime(dump_only=True)

    @validates('phone')
    def validate_phone(self,  value):
        if not value.isdigit():
            raise ValidationError("Phone number must contain only digits.")
        if len(value) != 10:
            raise ValidationError("Phone number must be exactly 10 digits long.")
        
class UserSchema(BaseUserSchema):
    pass

    

class AdminSchema(BaseUserSchema):
    pass


class AddressSchema(Schema):
    id = fields.Int(dump_only=True)
    street = fields.Str(required=True)
    city = fields.Str(required=True)
    state = fields.Str(required=True)
    postal_code = fields.Str(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)
    

    
    
class RestaurantSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1))
    cover_image = fields.String(required=False)
    description = fields.String(required=False)
    # Cuisines from Enum
    cuisines = fields.List(
        fields.String(validate=validate.OneOf([cuisine.value for cuisine in CuisineEnum])),
        required=True,
        validate=validate.Length(min=1, error="At least one cuisine must be provided.")
    )
    # Food Preferences from Enum
    food_preferences = fields.List(
        fields.String(validate=validate.OneOf([pref.value for pref in FoodPreferenceEnum])),
        required=True,
        validate=validate.Length(min=1, error="At least one food preference must be provided.")
    )
    # Nested Fields
    address = fields.Nested(AddressSchema, required=True)
    policy = fields.Nested(RestaurantPolicySchema, required=True)

    @validates('cover_image')
    def validate_cover_image(self, value):
        if value and not value.startswith(('http://', 'https://')):
            raise ValidationError("Cover image URL must start with http:// or https://")



class CuisineUpdateSchema(Schema):
    add = fields.List(
        fields.String(validate=validate.OneOf([cuisine.value for cuisine in CuisineEnum])),
        required=False,
        missing=[]
    )
    remove = fields.List(
        fields.String(validate=validate.OneOf([cuisine.value for cuisine in CuisineEnum])),
        required=False,
        missing=[]
    )

    @validates_schema
    def validate_cuisine_conflict(self, data, **kwargs):
        """Ensure cuisines are not present in both add & remove lists."""
        add_cuisines = set(data.get("add", []))
        remove_cuisines = set(data.get("remove", []))
        conflict = add_cuisines & remove_cuisines

        if conflict:
            raise ValidationError(f"Cuisines cannot be both added and removed: {', '.join(conflict)}")


class FoodPreferenceUpdateSchema(Schema):
    add = fields.List(
        fields.String(validate=validate.OneOf([food_preference.value for food_preference in FoodPreferenceEnum])),
        required=False,
        missing=[]
    )
    remove = fields.List(
        fields.String(validate=validate.OneOf([food_preference.value for food_preference in FoodPreferenceEnum])),
        required=False,
        missing=[]
    )

    @validates_schema
    def validate_food_preference_conflict(self, data, **kwargs):
        """Ensure food_preferences are not present in both add & remove lists."""
        add_food_preferences = set(data.get("add", []))
        remove_food_preferences = set(data.get("remove", []))
        conflict = add_food_preferences & remove_food_preferences

        if conflict:
            raise ValidationError(f"FoodPreferences cannot be both added and removed: {', '.join(conflict)}")



class TableTypeInfoSchema(Schema):
    table_type_id = fields.Int(required=True)
    count = fields.Int(required=True, validate=validate.Range(min=1))

class BookingRequestSchema(Schema):
    guest_count = fields.Int(required=True, validate=validate.Range(min=1))
    date = fields.Date(required=True)
    start_time = fields.Str(
        required=True,
        validate=validate.Regexp(r"^(?:[01]\d|2[0-3]):[0-5]\d$", error="Invalid time format. Use HH:MM")
    )
    table_type_info = fields.List(fields.Nested(TableTypeInfoSchema), required=True, validate=validate.Length(min=1))



    
class LoginSchema(Schema):
    name = fields.Str(required=True)
    password = fields.Str(required=True)