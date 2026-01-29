import logging
import re
from motor.motor_asyncio import AsyncIOMotorClient
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import LANG_PATTERNS, QUAL_PATTERNS

logger = logging.getLogger(__name__)

class Media:
    def __init__(self):
        self._client = AsyncIOMotorClient(MONGO_URI)
        self.db = self._client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]
        self.temp_col = self.db["temp_searches"]
        self.seq_col = self.db["sequences"]

    # ==========================================
    # 🔎 OPTIMIZED SEARCH LOGIC
    # ==========================================
    
    async def get_search_results(self, query, file_type=None, lang=None, quality=None, year=None, size_key=None, offset=0, limit=10):
        """
        Master Search Function handling ALL filters simultaneously.
        """
        # 1. Base Text Search (Regex)
        regex_query = re.escape(query)
        words = query.split()
        if len(words) > 1:
            # Matches words in any order
            regex_query = "".join(f"(?=.*{re.escape(w)})" for w in words)
        
        mongo_query = {
            "file_name": {"$regex": regex_query, "$options": "i"}
        }

        # 2. File Type Filter (Video/Document)
        if file_type and file_type != "None":
            mongo_query["file_type"] = file_type

        # 3. Language Filter (Smart Regex)
        if lang and lang != "None":
            key = lang.capitalize()
            if key in LANG_PATTERNS:
                pattern = LANG_PATTERNS[key]
                # Check both filename and caption
                mongo_query["$and"] = mongo_query.get("$and", []) + [
                    {"$or": [{"file_name": {"$regex": pattern}}, {"caption": {"$regex": pattern}}]}
                ]

        # 4. Quality Filter
        if quality and quality != "None":
            if quality in QUAL_PATTERNS:
                pattern = QUAL_PATTERNS[quality]
            else:
                pattern = re.compile(rf'\b{quality}\b', re.IGNORECASE)
            
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": pattern}}]

        # 5. Year Filter
        if year and year != "None":
            year_pattern = re.compile(rf'\b{year}\b')
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": year_pattern}}]

        # 6. Size Filter
        if size_key and size_key != "None":
            size_query = {}
            if size_key == "s": size_query = {"$lt": 524288000} # < 500MB
            elif size_key == "m": size_query = {"$gte": 524288000, "$lt": 1073741824} # 500MB-1GB
            elif size_key == "l": size_query = {"$gte": 1073741824, "$lt": 2147483648} # 1GB-2GB
            elif size_key == "xl": size_query = {"$gte": 2147483648} # > 2GB
            
            if size_query:
                mongo_query["file_size"] = size_query

        # Execute Query
        try:
            cursor = self.col.find(mongo_query)
            cursor.sort('_id', -1) # Newest First
            cursor.skip(offset).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return []

    async def get_unique_years(self, query):
        """Fetch years existing in the results for smart filtering"""
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

    # ... [Sequence functions, save_search_query, etc. same as before] ...
    # (Agar aapke paas already hai to wo code yahan rakhein)
    async def get_next_sequence(self):
        doc = await self.seq_col.find_one_and_update(
            {"_id": "search_id"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
        return doc["seq"]

    async def save_search_query(self, query, user_id):
        sid = await self.get_next_sequence()
        await self.temp_col.update_one(
            {"_id": sid}, {"$set": {"query": query, "user_id": user_id}}, upsert=True)
        return sid

    async def get_search_query(self, search_id):
        doc = await self.temp_col.find_one({"_id": int(search_id)})
        return doc['query'] if doc else None
    
    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

db = Media()
