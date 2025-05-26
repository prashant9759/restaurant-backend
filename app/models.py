from app import db
from datetime import datetime, timedelta

import json

# Mapping weekdays to numbers (0 = Monday, ..., 6 = Sunday)
WEEKDAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday",
            3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=False)
    # Unique removed for security reasons
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(50), nullable=False,
                     default='user')  # 'user' or 'admin'
    email_verification_code = db.Column(db.String(50))
    verification_code_sent_at = db.Column(db.DateTime, nullable=True)

    # ✅ New fields
    bio = db.Column(db.Text, nullable=True)  # A text field for user bio
    # Stores URL/path of profile image
    profile_image = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    is_email_verified = db.Column(db.Boolean, default=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), nullable=False, unique=False)
    # Unique removed for security reasons
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=True, unique=False)
    role = db.Column(db.String(50), nullable=False,
                     default='admin')  # 'user' or 'admin'
    email_verification_code = db.Column(db.String(50))
    verification_code_sent_at = db.Column(db.DateTime, nullable=True)

    # ✅ New fields
    bio = db.Column(db.Text, nullable=True)  # A text field for user bio
    # Stores URL/path of profile image
    profile_image = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
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
    # Max days a booking can be made in advance
    max_advance_days = db.Column(db.Integer, nullable=False)
    reservation_duration = db.Column(
        db.Integer, nullable=False)  # Duration in minutes

    def to_dict(self):
        return {
            "policy_id": self.id,
            "max_party_size": self.max_party_size,
            "max_advance_days": self.max_advance_days,
            "reservation_duration": self.reservation_duration
        }


class RestaurantOperatingHours(db.Model):
    """Stores different opening and closing times for each weekday."""
    __tablename__ = 'restaurant_operating_hours'
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id', ondelete='CASCADE'), nullable=False)
    # 0 (Monday) to 6 (Sunday)
    day_of_week = db.Column(db.Integer, nullable=False)
    opening_time = db.Column(db.Time, nullable=False)
    closing_time = db.Column(db.Time, nullable=False)

    restaurant = db.relationship(
        'Restaurant', backref='operating_hours', lazy=True)

    def to_dict(self):
        return {
            "operating_hour_id": self.id,
            # Convert number to weekday name
            "day_of_week": WEEKDAYS.get(self.day_of_week, "Unknown"),
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
    db.Column("restaurant_id", db.Integer, db.ForeignKey(
        "restaurant.id"), primary_key=True),
    db.Column("feature_id", db.Integer, db.ForeignKey(
        "feature.id"), primary_key=True)
)


restaurant_specialities = db.Table(
    "restaurant_specialties",
    db.Column("restaurant_id", db.Integer, db.ForeignKey(
        "restaurant.id"), primary_key=True),
    db.Column("specialty_id", db.Integer, db.ForeignKey(
        "speciality.id"), primary_key=True)
)


class Restaurant(db.Model):
    __tablename__ = 'restaurant'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cover_image = db.Column(db.String(255))
    # Stores restaurant phone number
    phone = db.Column(db.String(15), nullable=False, unique=False)
    # Represents cost level (e.g., 1 = cheap, 3 = expensive)
    average_cost_level = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(150), nullable=False)
    timezone = db.Column(db.String(100), nullable=False,
                         default="Asia/Kolkata")  # Example default
    description = db.Column(db.Text)
    rating = db.Column(db.Float, default=0.0)  # Stores average rating
    review_count = db.Column(db.Integer, default=0)  # Stores number of reviews

    admin_id = db.Column(db.Integer, db.ForeignKey(
        'admin.id', ondelete='CASCADE'), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant_policy.id', ondelete='CASCADE'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)  # Soft delete flag
    deleted_at = db.Column(db.DateTime, nullable=True)  # Track deletion time

    admin = db.relationship('Admin', backref='restaurants', lazy='joined')
    policy = db.relationship('RestaurantPolicy', uselist=False, lazy='joined')
    features = db.relationship(
        "Feature", secondary=restaurant_features, backref="restaurants")
    specialities = db.relationship(
        "Speciality", secondary=restaurant_specialities, backref="restaurants")

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
        table_types = TableType.query.filter_by(
            restaurant_id=self.id, is_deleted=False).all()
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
            "phone": self.phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,

            # Address Object
            "address": self.address,

            # Admin Object
            "admin": self.admin.to_dict(),
            "policy": self.policy.to_dict(),
            "operating_hours": [hour.to_dict() for hour in self.operating_hours] if self.operating_hours else [],
            "specialities": [{"speciality_id": s.id, "name": s.name} for s in self.specialities],
            "features": [{"feature_id": f.id, "name": f.name} for f in self.features],
            "review_count": self.review_count,
            "rating": self.rating,
            "reviews": [review.to_dict() for review in self.reviews]
        }


tableType_features = db.Table(
    "table_type_features",
    db.Column("table_type_id", db.Integer, db.ForeignKey(
        "table_type.id"), primary_key=True),
    db.Column("feature_id", db.Integer, db.ForeignKey(
        "feature.id"), primary_key=True)
)


class TableType(db.Model):
    __tablename__ = 'table_type'

    id = db.Column(db.Integer, primary_key=True)
    # e.g., "Two-seater", "Family Table"
    name = db.Column(db.String(50), nullable=False)
    minimum_capacity = db.Column(db.Integer, nullable=False)  # Number of seats
    maximum_capacity = db.Column(db.Integer, nullable=False)
    # Additional info like "Best for couples"
    description = db.Column(db.String(200))
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    cover_image = db.Column(db.String(255))
    shape = db.Column(db.String(30))
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        """Soft delete table type and its associated tables."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

        # Soft delete all related tables
        tables = TableInstance.query.filter_by(
            table_type_id=self.id, is_deleted=False).all()
        for table in tables:
            table.soft_delete()

        db.session.commit()

    features = db.relationship(
        "Feature", secondary=tableType_features, backref="table_types")
    restaurant = db.relationship("Restaurant", backref="table_types")

    def to_dict(self):
        return {
            "tabletype_id": self.id,
            "name": self.name,
            "minimum_capacity": self.minimum_capacity,
            "maximum_capacity": self.maximum_capacity,
            "description": self.description,
            "cover_image": self.cover_image,
            "is_deleted": self.is_deleted,
            "features": self.features,  # Return list of features
            "shape": self.shape,
            "features": [{"feature_id": f.id, "name": f.name} for f in self.features],
        }


class TableInstance(db.Model):
    __tablename__ = 'table_instance'
    id = db.Column(db.Integer, primary_key=True)
    table_type_id = db.Column(db.Integer, db.ForeignKey(
        'table_type.id'), nullable=False)
    # Unique ID within restaurant
    table_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)  # Number of seats
    # e.g., "Near window", "By the patio"
    location_description = db.Column(db.String(100))
    # Current availability status
    is_available = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Add relationship to availability records
    availability_records = db.relationship(
        'TableAvailability', backref='table', lazy='dynamic')

    def soft_delete(self):
        """Soft delete table instance."""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        db.session.commit()

    # Eagerly load table_type
    table_type = db.relationship('TableType', backref='tables', lazy='select')

    def to_dict(self):
        return {
            "table_id": self.id,
            "table_number": self.table_number,
            "location_description": self.location_description,
            "is_available": self.is_available,
            "is_deleted": self.is_deleted,
            "capacity": self.capacity
        }

    def calculate_efficiency(self, start_date, end_date):
        """Calculate table efficiency for a given date range."""
        # Get availability records for the date range
        availability_records = self.availability_records.filter(
            TableAvailability.date >= start_date,
            TableAvailability.date <= end_date
        ).all()

        # Get bookings for the date range
        bookings = Booking.query.join(BookingTable).filter(
            BookingTable.table_id == self.id,
            Booking.date >= start_date,
            Booking.date <= end_date
        ).all()

        # Calculate metrics
        total_available_slots = sum(
            record.available_slots for record in availability_records)
        total_booked_slots = sum(
            1 for booking in bookings if booking.status != 'cancelled')
        successful_bookings = sum(1 for booking in bookings if booking.status in [
                                  'completed', 'no_show'])

        # Calculate efficiency metrics
        if total_available_slots > 0:
            utilization_rate = (total_booked_slots /
                                total_available_slots) * 100
            success_rate = (successful_bookings / total_booked_slots *
                            100) if total_booked_slots > 0 else 0
            overall_efficiency = (successful_bookings /
                                  total_available_slots) * 100
        else:
            utilization_rate = 0
            success_rate = 0
            overall_efficiency = 0

        return {
            'total_available_slots': total_available_slots,
            'total_booked_slots': total_booked_slots,
            'successful_bookings': successful_bookings,
            'utilization_rate': utilization_rate,
            'success_rate': success_rate,
            'overall_efficiency': overall_efficiency
        }


class TableAvailability(db.Model):
    """Tracks daily availability of tables."""
    __tablename__ = 'table_availability'

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey(
        'table_instance.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    # Array of available slot start times
    available_slots = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add unique constraint to prevent duplicate records for same table and date
    __table_args__ = (
        db.UniqueConstraint('table_id', 'date', name='unique_table_date'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'table_id': self.table_id,
            'date': self.date.isoformat(),
            'available_slots': self.available_slots,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def update_availability_for_slot(cls, table_id, date, slot_time):
        """Update availability for a specific slot time."""
        # Get or create availability record
        availability = cls.query.filter_by(
            table_id=table_id,
            date=date
        ).first()

        if not availability:
            availability = cls(
                table_id=table_id,
                date=date,
                available_slots=[]
            )
            db.session.add(availability)

        # Check if table is available
        table = TableInstance.query.get(table_id)
        if not table or table.is_deleted:
            return

        # If table is available, add the slot
        if table.is_available:
            if slot_time.strftime("%H:%M") not in availability.available_slots:
                availability.available_slots.append(
                    slot_time.strftime("%H:%M"))
                db.session.commit()

    @classmethod
    def initialize_daily_availability(cls, table_id, date):
        """Initialize availability records for a table for a specific date."""
        table = TableInstance.query.get(table_id)
        if not table or table.is_deleted:
            return

        # Get restaurant operating hours
        operating_hours = RestaurantOperatingHours.query.filter_by(
            restaurant_id=table.table_type.restaurant_id,
            day_of_week=date.weekday()
        ).first()

        if not operating_hours:
            return

        # Create availability record
        availability = cls(
            table_id=table_id,
            date=date,
            available_slots=[]
        )
        db.session.add(availability)
        db.session.commit()

        # Schedule updates for each slot
        reservation_duration = table.table_type.restaurant.policy.reservation_duration
        current_time = operating_hours.opening_time

        while current_time < operating_hours.closing_time:
            slot_time = datetime.combine(date, current_time)
            # Schedule the update for this slot
            from app.tasks import update_table_availability
            update_table_availability.delay(table_id, date, slot_time)
            # Move to next slot
            current_time = (datetime.combine(date, current_time) +
                            timedelta(minutes=reservation_duration)).time()


class Booking(db.Model):
    __tablename__ = "booking"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10), nullable=False)  # Example: "18:00"
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # Name of the person making the booking
    customer_name = db.Column(db.String(100), nullable=True)
    # Phone number of the person making the booking
    customer_phone = db.Column(db.String(20), nullable=True)
    source = db.Column(
        db.Enum('online', 'walkin', name='booking_source_enum'),
        nullable=False
    )
    checkin_code = db.Column(db.String(10), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    guest_count = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.Enum('active', 'completed', 'cancelled',
                'no_show','pending', name='booking_status_enum'),
        nullable=False,
        default="active"
    )

    tables = db.relationship("BookingTable", back_populates="booking")
    user = db.relationship("User", backref="booking")
    restaurant = db.relationship("Restaurant", backref="bookings")


class BookingTable(db.Model):
    __tablename__ = "booking_table"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey(
        "booking.id"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey(
        "table_instance.id"), nullable=False)

    booking = db.relationship("Booking", back_populates="tables")
    table = db.relationship("TableInstance", backref="bookings")


class RestaurantLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        "restaurant.id"), nullable=False)
    liked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="likes")


class RestaurantReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        "restaurant.id"), nullable=False)
    rating = db.Column(db.Float, nullable=True)  # Rating (1.0-5.0 scale)
    review = db.Column(db.Text, nullable=True)  # Optional review text
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref="reviews")
    restaurant = db.relationship('Restaurant', backref='reviews')

    def to_dict(self):
        return {
            "review_id": self.id,
            "user_id": self.user_id,
            "rating": self.rating,
            "review_text": self.review,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# Association Tables
fooditem_offering = db.Table(
    'fooditem_offering',
    db.Column('food_item_id', db.Integer, db.ForeignKey(
        'food_item.id'), primary_key=True),
    db.Column('offering_period_id', db.Integer, db.ForeignKey(
        'food_offering_period.id'), primary_key=True)
)

fooditem_dietarytype = db.Table(
    'fooditem_dietarytype',
    db.Column('food_item_id', db.Integer, db.ForeignKey(
        'food_item.id'), primary_key=True),
    db.Column('dietary_type_id', db.Integer, db.ForeignKey(
        'dietary_type.id'), primary_key=True)
)


# Offering Periods (e.g., Breakfast, Lunch)
class FoodOfferingPeriod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    restaurant = db.relationship("Restaurant", backref="offering_periods")


# Categories (e.g., Daal, Chapati)
class FoodCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    restaurant = db.relationship("Restaurant", backref="food_categories")


# Dietary Types (e.g., Vegan, Eggish)
class DietaryType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey(
        'restaurant.id'), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    restaurant = db.relationship("Restaurant", backref="dietaryTypes")


# Main Food Items
class FoodItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    base_price = db.Column(db.Float)
    is_available = db.Column(db.Boolean, default=True)
    has_variants = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    food_category_id = db.Column(db.Integer, db.ForeignKey(
        'food_category.id'), nullable=False)
    category = db.relationship("FoodCategory", backref="food_items")

    offering_periods = db.relationship(
        'FoodOfferingPeriod',
        secondary=fooditem_offering,
        backref='food_items'
    )

    dietary_types = db.relationship(
        'DietaryType',
        secondary=fooditem_dietarytype,
        backref='food_items'
    )

    variants = db.relationship(
        "FoodItemVariant",
        backref="food_item",
        cascade="all, delete-orphan"
    )


# Optional Variants (e.g., Small/Medium/Large)
class FoodItemVariant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    food_item_id = db.Column(db.Integer, db.ForeignKey(
        'food_item.id'), nullable=False)


class FoodItemStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    food_item_id = db.Column(db.Integer, db.ForeignKey(
        'food_item.id'), nullable=False)
    food_item = db.relationship("FoodItem", backref="stock_entries")

    variant_id = db.Column(db.Integer, db.ForeignKey(
        'food_item_variant.id'), nullable=True)
    variant = db.relationship("FoodItemVariant", backref="stock_entries")

    current_stock = db.Column(db.Integer, nullable=False, default=0)
    threshold = db.Column(db.Integer, nullable=False,
                          default=0)  # for low-stock alerts

    last_updated = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReservationFoodOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey(
        'booking.id'), unique=True, nullable=False)
    reservation = db.relationship(
        "Booking", backref=db.backref("food_order", uselist=False))

    # Prevent changes after confirmation
    is_finalized = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Optional: total_price field, auto-calculated


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey(
        'reservation_food_order.id'), nullable=False)
    order = db.relationship("ReservationFoodOrder", backref="items")

    food_item_id = db.Column(db.Integer, db.ForeignKey(
        'food_item.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey(
        'food_item_variant.id'), nullable=True)

    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)  # cache snapshot of price

    food_item = db.relationship("FoodItem")
    variant = db.relationship("FoodItemVariant")


class TokenBlocklist(db.Model):
    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


























