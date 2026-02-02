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

    async def ensure_indexes(self):
        try:
            await self.col.create_index("file_unique_id", unique=True)
            await self.col.create_index("link_id")
            await self.col.create_index([("file_name", "text")])
            await self.temp_col.create_index("created_at", expireAfterSeconds=172800)
        except: pass

    # =====================================================
    # 🧠 SMART SEARCH ENGINE (ATLAS + FALLBACK)
    # =====================================================
    async def get_search_results(self, query, file_type=None, lang=None, quality=None, year=None, size_key=None, offset=0, limit=10):
        try:
            # 1️⃣ KOSHISH 1: Atlas Search (High-Tech)
            pipeline = [
                {
                    "$search": {
                        "index": "default",
                        "text": {
                            "query": query,
                            "path": "file_name",
                            "fuzzy": {"maxEdits": 2}
                        }
                    }
                }
            ]
            
            # Filters Setup
            match = {}
            if file_type and file_type != "None": match["file_type"] = file_type
            
            if size_key and size_key != "None":
                if size_key == "s": match["file_size"] = {"$lt": 524288000}
                elif size_key == "m": match["file_size"] = {"$gte": 524288000, "$lt": 1073741824}
                elif size_key == "l": match["file_size"] = {"$gte": 1073741824, "$lt": 2147483648}
                elif size_key == "xl": match["file_size"] = {"$gte": 2147483648}

            and_cond = []
            if lang and lang != "None":
                pat = LANG_PATTERNS.get(lang.capitalize())
                if pat: and_cond.append({"$or": [{"file_name": {"$regex": pat}}, {"caption": {"$regex": pat}}]})
            if quality and quality != "None":
                pat = QUAL_PATTERNS.get(quality, re.compile(rf'\b{quality}\b', re.IGNORECASE))
                and_cond.append({"file_name": {"$regex": pat}})
            if year and year != "None":
                and_cond.append({"file_name": {"$regex": re.compile(rf'\b{year}\b')}})

            if and_cond: match["$and"] = and_cond
            if match: pipeline.append({"$match": match})
            
            pipeline.extend([{"$skip": offset}, {"$limit": limit}])
            
            cursor = self.col.aggregate(pipeline)
            results = await cursor.to_list(length=limit)
            
            # ✅ Agar result mila, to return karo
            if results: return results
            
            # ❌ Agar result nahi mila, to Fallback trigger karo
            raise Exception("Zero results from Atlas")

        except Exception as e:
            # 2️⃣ KOSHISH 2: Simple Regex Search (Ye fail nahi hoti)
            return await self.get_search_results_fallback(query, file_type, lang, quality, year, size_key, offset, limit)

    # --- OLD SIMPLE SEARCH (Backup Plan) ---
    async def get_search_results_fallback(self, query, file_type, lang, quality, year, size_key, offset, limit):
        # Query Tod-Mod (Ex: "Avengers War" -> "Avengers.*War")
        regex = "".join(f"(?=.*{re.escape(w)})" for w in query.split())
        mongo_query = {"file_name": {"$regex": regex, "$options": "i"}}

        # Filters
        if file_type and file_type != "None": mongo_query["file_type"] = file_type
        
        if size_key and size_key != "None":
            if size_key == "s": mongo_query["file_size"] = {"$lt": 524288000}
            elif size_key == "m": mongo_query["file_size"] = {"$gte": 524288000, "$lt": 1073741824}
            elif size_key == "l": mongo_query["file_size"] = {"$gte": 1073741824, "$lt": 2147483648}
            elif size_key == "xl": mongo_query["file_size"] = {"$gte": 2147483648}

        if lang and lang != "None":
            pat = LANG_PATTERNS.get(lang.capitalize())
            if pat: 
                mongo_query["$and"] = mongo_query.get("$and", []) + [{"$or": [{"file_name": {"$regex": pat}}, {"caption": {"$regex": pat}}]}]
        
        if quality and quality != "None":
            pat = QUAL_PATTERNS.get(quality, re.compile(rf'\b{quality}\b', re.IGNORECASE))
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": pat}}]
            
        if year and year != "None":
            mongo_query["$and"] = mongo_query.get("$and", []) + [{"file_name": {"$regex": re.compile(rf'\b{year}\b')}}]

        cursor = self.col.find(mongo_query)
        cursor.sort('_id', -1)
        cursor.skip(offset).limit(limit)
        return await cursor.to_list(length=limit)

    # --- YEAR DETECTION ---
    async def get_unique_years(self, query):
        try:
            pipeline = [{"$match": {"file_name": {"$regex": query, "$options": "i"}}}, {"$limit": 50}, {"$project": {"file_name": 1}}]
            cursor = self.col.aggregate(pipeline)
            files = await cursor.to_list(length=50)
            years = set()
            pat = re.compile(r'\b(?:19|20)\d{2}\b')
            for f in files: years.update(pat.findall(f['file_name']))
            return sorted(list(years), reverse=True)
        except: return []

    # --- SAVE FILE ---
    async def save_file(self, message):
        try:
            file_info = get_file_details(message)
            if not file_info: return False
            if await self.col.find_one({'file_unique_id': file_info['file_unique_id']}): return False
            
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
        except: return False

    # --- UTILS ---
    async def get_next_sequence(self):
        doc = await self.seq_col.find_one_and_update({"_id": "search_id"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
        return doc["seq"]

    async def save_search_query(self, query, user_id):
        sid = await self.get_next_sequence()
        await self.temp_col.update_one({"_id": sid}, {"$set": {"query": query, "user_id": user_id}}, upsert=True)
        return sid

    async def get_search_query(self, search_id):
        doc = await self.temp_col.find_one({"_id": int(search_id)})
        return doc['query'] if doc else None
    
    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})
    
    async def delete_all_files(self):
        await self.col.delete_many({})

db = Media()
