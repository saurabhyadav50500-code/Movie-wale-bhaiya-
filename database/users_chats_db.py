import logging
import motor.motor_asyncio
from info import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

class UserChatsDB:
    def __init__(self):
        # 1. OPTIMIZED CONNECTION POOLING 🚀
        # minPoolSize=10: Keeps 10 connections ready (Instant clicks)
        # maxPoolSize=100: Handles high load spikes
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGO_URI,
            minPoolSize=10,
            maxPoolSize=100,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.client[DATABASE_NAME]
        self.col = self.db["users_chats"]
        
        # 2. IN-MEMORY LRU CACHE 🧠
        # Stores group settings to save Database Query Credits & RAM
        self._cache = {} 
        self._MAX_CACHE_SIZE = 200 # Strict limit for 512MB RAM

    # --- 🧠 SMART CACHE MANAGER ---
    
    def _update_cache(self, chat_id, data):
        """Updates cache and maintains the size limit (LRU Logic)."""
        if chat_id in self._cache:
            # If exists, remove to re-insert at the end (Mark as Recently Used)
            self._cache.pop(chat_id)
        
        self._cache[chat_id] = data
        
        # If cache grows too big, remove the OLDER item (First item)
        if len(self._cache) > self._MAX_CACHE_SIZE:
            first_key = next(iter(self._cache))
            self._cache.pop(first_key)

    def _get_from_cache(self, chat_id):
        """Gets from cache and moves to end (Mark as Recently Used)."""
        if chat_id in self._cache:
            data = self._cache.pop(chat_id)
            self._cache[chat_id] = data
            return data
        return None

    # --- 👥 USER MANAGEMENT ---

    async def add_user(self, user_id, first_name):
        """Adds a user to database if not exists."""
        try:
            # Upsert is safer/faster than find + insert
            await self.col.update_one(
                {"id": user_id},
                {"$set": {"first_name": first_name}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    # --- 🛡️ GROUP SETTINGS (With Caching) ---

    async def get_group_status(self, chat_id):
        """
        Fetches group settings (Auto-Delete, Welcome, etc.)
        Uses RAM Cache first, then DB.
        """
        # 1. Check RAM Cache First
        cached_data = self._get_from_cache(chat_id)
        if cached_data:
            return cached_data

        # 2. If not in RAM, Fetch from MongoDB
        try:
            chat = await self.col.find_one({"id": int(chat_id)})
            
            # Default Settings if group not found
            if not chat:
                chat = {
                    "id": int(chat_id),
                    "auto_delete": True,     # Example Setting
                    "auto_delete_time": 600, # 10 Minutes
                    "welcome_enabled": True
                }
                # Optional: Auto-save new group to DB? 
                # await self.add_group(chat_id) 

            # 3. Save to RAM Cache
            self._update_cache(chat_id, chat)
            return chat
            
        except Exception as e:
            logger.error(f"Error getting group status: {e}")
            return None

    async def update_group_settings(self, chat_id, setting_name, value):
        """
        Updates a specific setting in DB and updates Cache instantly.
        """
        try:
            # 1. Update Database
            await self.col.update_one(
                {"id": int(chat_id)},
                {"$set": {setting_name: value}},
                upsert=True
            )
            
            # 2. Update Cache (Write-Through)
            # Fetch current cache or empty dict
            current_data = self._get_from_cache(chat_id) or {"id": int(chat_id)}
            current_data[setting_name] = value
            self._update_cache(chat_id, current_data)
            
            return True
        except Exception as e:
            logger.error(f"Error updating setting: {e}")
            return False

    async def get_all_users(self):
        """Helper for Broadcast (No Cache needed usually)"""
        return self.col.find({})

db_users = UserChatsDB()
