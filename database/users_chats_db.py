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

    async def is_premium(self, user_id):
        """Check karega ki user premium hai ya nahi"""
        user = await self.col.find_one({"id": user_id})
        if user and user.get("premium_status", False):
            return True
        return False

    # ==========================================
    # 🔗 ADVANCED SHORTENER & VERIFICATION DB
    # ==========================================

    async def get_group_shortener_settings(self, chat_id):
        """Fetch group's advanced shortener config"""
        chat = await self.get_group_status(chat_id)
        default_settings = {
            "mode": "smart", # Modes: 'smart', 'together'
            "slots": {
                "1": {"site": "", "api": "", "time": 86400}, # Default 24h
                "2": {"site": "", "api": "", "time": 43200}, # Default 12h
                "3": {"site": "", "api": "", "time": 43200}  # Default 12h
            }
        }
        if chat and "shortener_config" in chat:
            # Merge defaults if some keys are missing
            existing = chat["shortener_config"]
            if "slots" not in existing:
                existing["slots"] = default_settings["slots"]
            return existing
        return default_settings

    async def update_shortener_slot(self, chat_id, slot, site, api):
        """Update specific shortener slot (1, 2, or 3)"""
        settings = await self.get_group_shortener_settings(chat_id)
        if str(slot) not in settings["slots"]:
            settings["slots"][str(slot)] = {"time": 86400}
        settings["slots"][str(slot)]["site"] = site
        settings["slots"][str(slot)]["api"] = api
        # Utilizing existing cached update method!
        await self.update_group_settings(chat_id, "shortener_config", settings)

    async def update_shortener_mode(self, chat_id, mode):
        """Update shortener mode (smart/together)"""
        settings = await self.get_group_shortener_settings(chat_id)
        settings["mode"] = mode
        await self.update_group_settings(chat_id, "shortener_config", settings)

    async def update_shortener_time(self, chat_id, slot, time_in_sec):
        """Update duration for a specific slot"""
        settings = await self.get_group_shortener_settings(chat_id)
        if str(slot) not in settings["slots"]:
            settings["slots"][str(slot)] = {"site": "", "api": ""}
        settings["slots"][str(slot)]["time"] = int(time_in_sec)
        await self.update_group_settings(chat_id, "shortener_config", settings)

    # --- User Verification Status ---
    async def get_verify_status(self, user_id, chat_id):
        """Check user verification timestamps"""
        user = await self.col.find_one({"id": user_id})
        if user and "verification" in user:
            # chat_id as string because MongoDB keys are strings
            return user["verification"].get(str(chat_id), {})
        return {}

    async def update_verify_status(self, user_id, chat_id, level):
        """Mark a level as verified by saving current exact timestamp"""
        await self.col.update_one(
            {"id": user_id},
            {"$set": {f"verification.{chat_id}.level_{level}_time": time.time()}},
            upsert=True
        )

db_users = UserChatsDB()
