import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB_NAME", "bot_happy")

_client = MongoClient(MONGODB_URI) if MONGODB_URI else None
db = _client[DB_NAME] if _client is not None else None

categories_collection = db["categories"] if db is not None else None
products_collection = db["products"] if db is not None else None
sessions_collection = db["sessions"] if db is not None else None