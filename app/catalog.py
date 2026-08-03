from bson import ObjectId
from app.db import categories_collection, products_collection


def get_categories(limit: int = 3):
    """Trae hasta `limit` categorías (WhatsApp permite máximo 3 botones por mensaje)."""
    return list(categories_collection.find().limit(limit))


def get_category_by_id(category_id: str):
    try:
        return categories_collection.find_one({"_id": ObjectId(category_id)})
    except Exception:
        return None


def get_products_by_category(category_id: str, limit: int = 3):
    try:
        cat_oid = ObjectId(category_id)
    except Exception:
        return []
    return list(products_collection.find({"category_id": cat_oid}).limit(limit))


def get_product_by_id(product_id: str):
    try:
        return products_collection.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return None
