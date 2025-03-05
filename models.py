from enum import unique, Enum


from db import db
from datetime import datetime
from sqlalchemy import UniqueConstraint,Text
from sqlalchemy.dialects.mysql import JSON

import json

# Define Food Preference Enum
class FoodPreferenceEnum(str, Enum):
    VEG = "Veg"
    NON_VEG = "Non-Veg"
    VEGAN = "Vegan"



# Define Cuisine Enum
class CuisineEnum(str, Enum):
    ITALIAN = "Italian"
    CHINESE = "Chinese"
    INDIAN = "Indian"
    MEXICAN = "Mexican"
    JAPANESE = "Japanese"
    FRENCH = "French"
    THAI = "Thai"
    AMERICAN = "American"
    




# Mapping weekdays to numbers (0 = Monday, ..., 6 = Sunday)
WEEKDAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}



class TableShape(Enum):
    ROUND = "Round"
    SQUARE = "Square"
    RECTANGLE = "Rectangle"
    OVAL = "Oval"





class CityStateModel(db.Model):
    __tablename__ = "city_states"
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False, unique=True)
 
    
    def to_dict(self):
        return {
            "id": self.id,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code
        }



class User(db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=False, unique=False)
    password = db.Column(db.String(200), nullable=False)  # Unique removed for security reasons
    phone = db.Column(db.String(20), nullable=True, unique=False)
    role = db.Column(db.String(50), nullable=False, default='user')  # 'user' or 'admin'
    
    # ✅ New fields
    bio = db.Column(db.Text, nullable=True)  # A text field for user bio
    profile_image = db.Column(db.String(255), nullable=True)  # Stores URL/path of profile image
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)  # Soft delete flag
    deleted_at = db.Column(db.DateTime, nullable=True)  # Track deletion time

    def soft_delete(self):
        """Mark user as deleted instead of removing."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()

    def to_dict(self):
        return {
            "user_id": self.id,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "bio": self.bio,
            "profile_image": self.profile_image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }



class Admin(db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=False, unique=False)
    password = db.Column(db.String(200), nullable=False)  # Unique removed for security reasons
    phone = db.Column(db.String(20), nullable=True, unique=False)
    role = db.Column(db.String(50), nullable=False, default='admin')  # 'user' or 'admin'
    
    # ✅ New fields
    bio = db.Column(db.Text, nullable=True)  # A text field for user bio
    profile_image = db.Column(db.String(255), nullable=True)  # Stores URL/path of profile image
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)  # Soft delete flag
    deleted_at = db.Column(db.DateTime, nullable=True)  # Track deletion time

    def soft_delete(self):
        """Mark user as deleted instead of removing."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()

    def to_dict(self):
        return {
            "admin_id": self.id,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "bio": self.bio,
            "profile_image": self.profile_image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }



class RestaurantPolicy(db.Model):
    __tablename__ = 'restaurant_policy'
    id = db.Column(db.Integer, primary_key=True)
    max_party_size = db.Column(db.Integer, nullable=False)
    max_advance_days = db.Column(db.Integer, nullable=False)  # Max days a booking can be made in advance
    reservation_duration = db.Column(db.Integer, nullable=False)  # Duration in minutes

    # Merging Cancellation Policy
    free_cancellation_window = db.Column(db.Integer, nullable=False, default=120)  # In minutes (e.g., 120 means 2 hours)
    late_cancellation_fee = db.Column(db.Float, nullable=False, default=10.0)  # $10 per person for late cancellation/no-show

    def to_dict(self):
        return {
            "policy_id": self.id,
            "max_party_size": self.max_party_size,
            "max_advance_days": self.max_advance_days,
            "reservation_duration": self.reservation_duration,
            "free_cancellation_window": self.free_cancellation_window,
            "late_cancellation_fee": self.late_cancellation_fee
        }



class RestaurantOperatingHours(db.Model):
    """Stores different opening and closing times for each weekday."""
    __tablename__ = 'restaurant_operating_hours'
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id', ondelete='CASCADE'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0 (Monday) to 6 (Sunday)
    opening_time = db.Column(db.Time, nullable=False)  
    closing_time = db.Column(db.Time, nullable=False)

    restaurant = db.relationship('Restaurant', backref='operating_hours', lazy=True)

    def to_dict(self):
        return {
            "operating_hour_id":self.id,
            "day_of_week": WEEKDAYS.get(self.day_of_week, "Unknown"),  # Convert number to weekday name
            "opening_time": self.opening_time.strftime("%H:%M"),
            "closing_time": self.closing_time.strftime("%H:%M")
        }




class Feature(db.Model):
    __tablename__ = 'feature'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100),  nullable=False)



class Speciality(db.Model):
    __tablename__ = 'speciality'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)



restaurant_features = db.Table(
    "restaurant_features",
    db.Column("restaurant_id", db.Integer, db.ForeignKey("restaurant.id"), primary_key=True),
    db.Column("feature_id", db.Integer, db.ForeignKey("feature.id"), primary_key=True)
)



restaurant_specialities = db.Table(
    "restaurant_specialties",
    db.Column("restaurant_id", db.Integer, db.ForeignKey("restaurant.id"), primary_key=True),
    db.Column("specialty_id", db.Integer, db.ForeignKey("speciality.id"), primary_key=True)
)



class Restaurant(db.Model):
    __tablename__ = 'restaurant'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cover_image = db.Column(db.String(255))
    phone = db.Column(db.String(15), nullable=False, unique=False)  # Stores restaurant phone number
    average_cost_level = db.Column(db.Integer, nullable=False)  # Represents cost level (e.g., 1 = cheap, 3 = expensive)
    description = db.Column(db.Text)
    rating = db.Column(db.Float, default=0.0)  # Stores average rating
    review_count = db.Column(db.Integer, default=0)  # Stores number of reviews
    
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id', ondelete='CASCADE'), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey('restaurant_policy.id', ondelete='CASCADE'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)  # Soft delete flag
    deleted_at = db.Column(db.DateTime, nullable=True)  # Track deletion time

    # Address fields
    street = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    city_state_id = db.Column(db.Integer, db.ForeignKey('city_states.id'), nullable=False)

    admin = db.relationship('Admin', backref='restaurants', lazy='joined')
    city_state = db.relationship('CityStateModel', lazy='joined')
    policy = db.relationship('RestaurantPolicy', uselist=False, lazy='joined')
    features = db.relationship("Feature", secondary=restaurant_features, backref="restaurants")
    specialities = db.relationship("Speciality", secondary=restaurant_specialities, backref="restaurants")


    cuisines = db.relationship(
        'CuisineType',
        secondary='restaurant_cuisine',
        backref='restaurants',
        lazy='joined'
    )

    food_preferences = db.relationship(
        'FoodPreferenceType',
        secondary='restaurant_food_preference',
        backref='restaurants',
        lazy='joined'
    )
    
    
    def soft_delete(self):
        """Soft delete restaurant and its related table types & tables."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        
        # Get IDs of associated features & specialities before clearing
        feature_ids = [feature.id for feature in self.features]
        speciality_ids = [speciality.id for speciality in self.specialities]

        # Remove associations from the junction tables
        self.features.clear()
        self.specialities.clear()

        # Check and delete features that are no longer used by any restaurant
        for feature_id in feature_ids:
            feature = Feature.query.get(feature_id)
            if feature and not feature.restaurants:  # If no restaurant is linked
                db.session.delete(feature)

        # Check and delete specialities that are no longer used by any restaurant
        for speciality_id in speciality_ids:
            speciality = Speciality.query.get(speciality_id)
            if speciality and not speciality.restaurants:  # If no restaurant is linked
                db.session.delete(speciality)

        # Soft delete related table types
        table_types = TableType.query.filter_by(restaurant_id=self.id, is_deleted=False).all()
        for table_type in table_types:
            table_type.soft_delete()

        db.session.commit()

    def to_dict(self):
        return {
            "restaurantId": self.id,
            "name": self.name,
            "description": self.description,
            "cover_image": self.cover_image,
            "average_cost_level": self.average_cost_level,
            "phone":self.phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,

            # Address Object
            "address": {
                "city_state_id": self.city_state_id,
                "street": self.street,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "city": self.city_state.city if self.city_state else None,
                "state": self.city_state.state if self.city_state else None,
                "postal_code": self.city_state.postal_code if self.city_state else None
            },

            # Admin Object
            "admin": self.admin.to_dict(),
            "cuisines": [cuisine.name for cuisine in self.cuisines] if self.cuisines else [],
            "food_preferences": [pref.name for pref in self.food_preferences] if self.food_preferences else [],
            "policy": self.policy.to_dict(),
            "operating_hours": [hour.to_dict() for hour in self.operating_hours] if self.operating_hours else [],
            "specialities": [{"speciality_id": s.id, "name": s.name} for s in self.specialities],
            "features": [{"feature_id": f.id, "name": f.name} for f in self.features],
            "review_count":self.review_count,
            "rating":self.rating,
            "reviews":[review.to_dict() for review in  self.reviews]
        }



tableType_features = db.Table(
    "table_type_features",
    db.Column("table_type_id", db.Integer, db.ForeignKey("table_type.id"), primary_key=True),
    db.Column("feature_id", db.Integer, db.ForeignKey("feature.id"), primary_key=True)
)



class TableType(db.Model):
    __tablename__ = 'table_type'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., "Two-seater", "Family Table"
    minimum_capacity = db.Column(db.Integer, nullable=False)  # Number of seats
    maximum_capacity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200))  # Additional info like "Best for couples"
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    reservation_fees = db.Column(db.Float, nullable=False, default=0)
    cover_image = db.Column(db.String(255))
    shape = db.Column(db.Enum(TableShape), nullable=False)  # Added shape field
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
        
    def soft_delete(self):
        """Soft delete table type and its associated tables."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

        # Soft delete all related tables
        tables = TableInstance.query.filter_by(table_type_id=self.id, is_deleted=False).all()
        for table in tables:
            table.soft_delete()

        db.session.commit()
    
    __table_args__ = (UniqueConstraint('name', 'restaurant_id', name='_name_restaurant_uc'),)
    
    features = db.relationship("Feature", secondary=tableType_features, backref="table_types")
    restaurant = db.relationship("Restaurant", backref="table_types")

    def to_dict(self):
        return {
            "tabletype_id": self.id,
            "name": self.name,
            "minimum_capacity": self.minimum_capacity,
            "maximum_capacity": self.maximum_capacity,
            "description": self.description,
            "reservation_fees": self.reservation_fees,
            "cover_image": self.cover_image,
            "features": self.features, # Return list of features
            "shape": self.shape.name if self.shape else None,  # Convert Enum to string
            "features": [{"feature_id": f.id, "name": f.name} for f in self.features],
        }



class TableInstance(db.Model):
    __tablename__ = 'table_instance'
    id = db.Column(db.Integer, primary_key=True)
    table_type_id = db.Column(db.Integer, db.ForeignKey('table_type.id'), nullable=False)
    table_number = db.Column(db.String(20), nullable=False)  # Unique ID within restaurant
    location_description = db.Column(db.String(100))  # e.g., "Near window", "By the patio"
    is_available = db.Column(db.Boolean, default=True)  # Track table availability
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        """Soft delete table instance."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()
        
    __table_args__ = (UniqueConstraint('table_number', 'table_type_id', name='_table_number_table_type_id_uc'),)
    
    # Eagerly load table_type
    table_type = db.relationship('TableType', backref='tables', lazy='select')
    
    def to_dict(self):
        return {
            "table_id": self.id,
            "table_number": self.table_number,
            "location_description": self.location_description,
            "is_available": self.is_available
        }


class Booking(db.Model):
    __tablename__ = "booking"
    
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)  # Example: "18:00"
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    guest_count = db.Column(db.Integer, nullable = False)
    status = db.Column(db.String(30), nullable = False, default="active")
    
    tables = db.relationship("BookingTable", back_populates="booking")
    user = db.relationship("User", backref="booking")
    
     # ✅ Add a relationship to access restaurant details directly
    restaurant = db.relationship("Restaurant", backref="bookings")


class BookingTable(db.Model):  
    __tablename__ = "booking_table"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey("table_instance.id"), nullable=False)

    booking = db.relationship("Booking", back_populates="tables")
    table = db.relationship("TableInstance", backref="bookings")




class CuisineType(db.Model):
    __tablename__ = 'cuisine_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # e.g., 'Veg', 'Non-Veg', 'Vegan'



class FoodPreferenceType(db.Model):
    __tablename__ = 'food_preference_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # e.g., 'Veg', 'Non-Veg', 'Vegan'



class RestaurantCuisine(db.Model):
    __tablename__ = 'restaurant_cuisine'
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), primary_key=True)
    cuisine_type_id = db.Column(db.Integer, db.ForeignKey('cuisine_type.id'), primary_key=True)
    
    
class RestaurantFoodPreference(db.Model):
    __tablename__ = 'restaurant_food_preference'
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), primary_key=True)
    food_preference_id = db.Column(db.Integer, db.ForeignKey('food_preference_type.id'), primary_key=True)



class RestaurantLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    liked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship("User", backref="likes")
    restaurant = db.relationship("Restaurant", backref="likes")
    
    
class RestaurantReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    rating = db.Column(db.Float, nullable=True)  # Rating (1.0-5.0 scale)
    review = db.Column(db.Text, nullable=True)  # Optional review text
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="reviews")
    restaurant = db.relationship("Restaurant", backref="reviews")

    def to_dict(self):
        return {
            "review_id": self.id,
            "user_id": self.user_id,
            "restaurant_id": self.restaurant_id,
            "rating": self.rating,
            "review_text": self.review,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }




class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
  
  
    
