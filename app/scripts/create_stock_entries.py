from app import db
from app.models import Restaurant, FoodItem, FoodItemVariant, FoodItemStock
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_stock_entries_for_restaurant(restaurant_id):
    try:
        # Get the restaurant
        restaurant = Restaurant.query.get(restaurant_id)
        if not restaurant:
            logger.error(f"Restaurant with ID {restaurant_id} not found")
            return

        logger.info(f"Processing restaurant: {restaurant.name}")

        # Get all food items for this restaurant
        food_items = (
            FoodItem.query
            .join(FoodItem.category)
            .filter(
                FoodItem.category.has(restaurant_id=restaurant_id),
                FoodItem.is_deleted == False
            )
            .all()
        )

        logger.info(f"Found {len(food_items)} food items")

        for food_item in food_items:
            try:
                logger.info(f"Processing food item: {food_item.name}")

                if food_item.has_variants:
                    # Get all variants for this food item
                    variants = FoodItemVariant.query.filter_by(
                        food_item_id=food_item.id,
                        is_deleted=False
                    ).all()

                    logger.info(
                        f"Found {len(variants)} variants for {food_item.name}")

                    for variant in variants:
                        # Check if stock entry already exists
                        existing_entry = FoodItemStock.query.filter_by(
                            food_item_id=food_item.id,
                            variant_id=variant.id
                        ).first()

                        if not existing_entry:
                            # Create new stock entry for variant
                            stock_entry = FoodItemStock(
                                food_item_id=food_item.id,
                                variant_id=variant.id,
                                current_stock=0,  # Default to 0
                                threshold=10  # Default threshold
                            )
                            db.session.add(stock_entry)
                            logger.info(
                                f"Created stock entry for {food_item.name} - variant: {variant.name}")
                else:
                    # Check if stock entry already exists for non-variant item
                    existing_entry = FoodItemStock.query.filter_by(
                        food_item_id=food_item.id,
                        variant_id=None
                    ).first()

                    if not existing_entry:
                        # Create new stock entry for non-variant item
                        stock_entry = FoodItemStock(
                            food_item_id=food_item.id,
                            current_stock=0,  # Default to 0
                            threshold=10  # Default threshold
                        )
                        db.session.add(stock_entry)
                        logger.info(
                            f"Created stock entry for {food_item.name}")

            except Exception as e:
                logger.error(
                    f"Error processing food item {food_item.id}: {str(e)}")
                continue

        # Commit all changes
        db.session.commit()
        logger.info("Successfully created all stock entries")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        db.session.rollback()


if __name__ == "__main__":
    # This will be used when running the script directly
    restaurant_id = input("Enter restaurant ID: ")
    create_stock_entries_for_restaurant(int(restaurant_id))
