# info.py
import os

API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
MONGO_URI = os.environ.get("MONGO_URI", "your_mongo_uri")
ADMINS = [int(id) for id in os.environ.get("ADMINS", "12345678").split()]
DATABASE_NAME = "Cluster0"
COLLECTION_NAME = "files"
