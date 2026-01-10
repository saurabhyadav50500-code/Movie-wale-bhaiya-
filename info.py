# info.py
import os

API_ID = int(os.environ.get("API_ID", "34119293"))
API_HASH = os.environ.get("API_HASH", "ebea85e712484252c681be91348fdc85")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7956005223:AAGlqJdNnOizY-ijdcjldQsVEFYYP9LojPs")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Sur67:Sur67@cluster0.qh4c56q.mongodb.net/?retryWrites=true&w=majority")
ADMINS = [int(id) for id in os.environ.get("ADMINS", "847367333 1729007340").replace(',', ' ').split()]
DATABASE_NAME = "Cluster0"
COLLECTION_NAME = "files"
