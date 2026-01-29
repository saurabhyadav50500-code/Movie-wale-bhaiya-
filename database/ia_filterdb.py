import logging
import re
from motor.motor_asyncio import AsyncIOMotorClient
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id, LANG_PATTERNS, QUAL_PATTERNS

logger = logging.getLogger(__name__)

class Media:
    def __init__(self):
        self._client = AsyncIOMotorClient(MONGO_URI)
        self.db = self._client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]
        self.temp_col = self.db["temp_searches"]
        self.seq_col = self.db["sequences"]

    # ==========================================
    # 🛠️ INDEXES & MAINTENANCE
    # ==========================================
    async def ensure_indexes(self):
        """Creates necessary database indexes."""
        try:
            await self.col.create_index("file_unique_id", unique=True)
            await self.col.create_index("link_id")
            await self.col.create_index([("file_name", "text")])
            await self.temp_col.create_index("created_at", expireAfterSeconds=172800)
            logger.info("✅ Database Indexes Created Successfully.")
        except Exception as e:
            logger.error(f"❌ Error creating index: {e}")

    # ==========================================
    # 🔎 SEARCH LOGIC (Optimized)
    # ==========================================
    async def get_search_results(self, query, file_type=None, lang=None, quality=None, year=None, size_key=None, offset=0, limit=10):
        """Master Search Function."""
        # 1. Base Text Search
        regex_query = re.escape(query)
        words = query.split()
        if len(words) > 1:
            regex_query = "".join(f"(?=.*{re.escape(w)})" for w in words)
        
        mongo_query = {
            "file_name": {"$regex": regex_query, "$options": "i"}
        }

        # 2. File Type
        if file_type and file_type != "None":
            mongo_query["file_type"] = file_type

        # 3. Language
        if lang and lang != "None":
            key = lang.capitalize()
            if key in LANG_PATTERNS:
                pattern = LANG_PATTERNS[key]
                mongo_query["$and"] = mongo_query.get("$and", []) + [
                    {"$or": [{"file_name": {"$regex": pattern}}, {"caption": {"$regex": pattern}}]}
                ]

        # 4. Quality
        if quality and quality != "None":
            if quality in QUAL_PATTERNS:
                pattern = QUAL_PATTERNS[quality]
            else:
                pattern = re.compile(rf'\b{quality}\b', re.IGNORECASE)
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": pattern}}]

        # 5. Year
        if year and year != "None":
            year_pattern = re.compile(rf'\b{year}\b')
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": year_pattern}}]

        # 6. Size
        if size_key and size_key != "None":
            size_query = {}
            if size_key == "s": size_query = {"$lt": 524288000}
            elif size_key == "m": size_query = {"$gte": 524288000, "$lt": 1073741824}
            elif size_key == "l": size_query = {"$gte": 1073741824, "$lt": 2147483648}
            elif size_key == "xl": size_query = {"$gte": 2147483648}
            
            if size_query:
                mongo_query["file_size"] = size_query

        try:
            cursor = self.col.find(mongo_query)
            cursor.sort('_id', -1)
            cursor.skip(offset).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return []

    async def get_unique_years(self, query):
        """Fetch years from results."""
        regex_query = re.escape(query)
        pipeline = [
            {"$match": {"file_name": {"$regex": regex_query, "$options": "i"}}},
            {"$limit": 50}, 
            {"$project": {"file_name": 1}}
        ]
        try:
            cursor = self.col.aggregate(pipeline)
            files = await cursor.to_list(length=50)
            years = set()
            pattern = re.compile(r'\b(19|20)\d{2}\b')
            for f in files:
                matches = pattern.findall(f['file_name'])
                years.update(matches)
            return sorted(list(years), reverse=True)
        except:
            return []

    # ==========================================
    # 💾 FILE SAVING & UTILS
    # ==========================================
    async def get_next_sequence(self):
        doc = await self.seq_col.find_one_and_update(
            {"_id": "search_id"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
        return doc["seq"]

    async def save_search_query(self, query, user_id):
        sid = await self.get_next_sequence()
        # Clean text helper
        def clean_text(text):
            if not text: return ""
            text = text.lower()
            text = re.sub(r'https?://\S+|www\.\S+', '', text)
            return re.sub(r'\s+', ' ', text).strip()
            
        await self.temp_col.update_one(
            {"_id": sid}, {"$set": {"query": clean_text(query), "user_id": user_id}}, upsert=True)
        return sid

    async def get_search_query(self, search_id):
        doc = await self.temp_col.find_one({"_id": int(search_id)})
        return doc['query'] if doc else None
    
    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def save_file(self, message):
        """Saves a file to DB."""
        file_info = get_file_details(message)
        if not file_info: return False

        # Check Duplicate
        if await self.col.find_one({'file_unique_id': file_info['file_unique_id']}):
            return False

        doc = {
            'file_id': file_info['file_id'],
            'file_unique_id': file_info['file_unique_id'],
            'file_name': file_info['file_name'],
            'file_size': file_info['file_size'],
            'file_type': file_info['file_type'],
            'mime_type': file_info['mime_type'],
            'caption': message.caption or "",
            'chat_id': message.chat.id,
            'message_id': message.id,
            'link_id': generate_link_id()
        }
        await self.col.insert_one(doc)
        return True

    async def delete_all_files(self):
        await self.col.delete_many({})

db = Media()
