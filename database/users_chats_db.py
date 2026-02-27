import logging
import time
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

    # --- 🔗 SHORTENER & VERIFICATION LOGIC ---

    async def get_group_shortener(self, chat_id):
        """Group ki shortener settings fetch karega"""
        chat = await self.get_group_status(chat_id)
        if chat:
            return {
                "shortener_site": chat.get("shortener_site", "api.shareus.io"),
                "shortener_api": chat.get("shortener_api", ""),
                "verify_time": chat.get("verify_time", 86400), # 24 hours default
                "is_active": chat.get("shortener_active", False),
                "verify_levels": chat.get("verify_levels", 1) # Default 1, max 3
            }
        return None

    async def is_premium(self, user_id):
        """Check karega ki user premium hai ya nahi"""
        user = await self.col.find_one({"id": user_id})
        if user and user.get("premium_status", False):
            return True
        return False

    async def get_verify_status(self, user_id, chat_id):
        """User ki current verification status check karega"""
        user = await self.col.find_one({"id": user_id})
        if user and "verification" in user:
            # chat_id ko string mein convert karke get karte hain kyunki MongoDB keys string hoti hain
            return user["verification"].get(str(chat_id), {})
        return {}

    async def update_verify_status(self, user_id, chat_id, level, verify_time):
        """Verification level aur expiry time update karega"""
        expiry_time = time.time() + verify_time
        await self.col.update_one(
            {"id": user_id},
            {"$set": {
                f"verification.{chat_id}.level_{level}_done": True,
                f"verification.{chat_id}.expiry_time": expiry_time
            }},
            upsert=True
        )

db_users = UserChatsDB()
