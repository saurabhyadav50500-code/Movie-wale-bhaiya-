import logging
import re
from motor.motor_asyncio import AsyncIOMotorClient
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id, LANG_PATTERNS, QUAL_PATTERNS, clean_filename, standardize_tv_tags

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
    # 🧠 SUPER AGGRESSIVE SEARCH (SPELLING KILLER)
    # =====================================================
    async def get_search_results(self, query, file_type=None, lang=None, quality=None, year=None, size_key=None, sort_key=None, offset=0, limit=10):
        try:
            # 🆕 1. QUERY STANDARDIZATION & DUPLICATE REMOVAL
            query = standardize_tv_tags(query)
            
            # Duplicate words ko hatai jaise ki "e05 E05 episode 5" => "E05"
            query = " ".join(list(dict.fromkeys(query.split())))

            # 1️⃣ ATLAS SEARCH (High Tolerance)
            pipeline = [
                {
                    "$search": {
                        "index": "default",
                        "text": {
                            "query": query,
                            "path": ["file_name", "caption", "search_text"], # 🌟 search_text added
                            "fuzzy": {
                                "maxEdits": 0,       
                                "prefixLength": 0,   
                                "maxExpansions": 100 
                            }
                        }
                    }
                }
            ]
            
            # --- FILTERS ---
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
            
            # --- SORTING LOGIC (ATLAS) ---
            if sort_key and sort_key != "None":
                if sort_key == "new": pipeline.append({"$sort": {"_id": -1}})   # Newest First
                elif sort_key == "old": pipeline.append({"$sort": {"_id": 1}})    # Oldest First
                elif sort_key == "max": pipeline.append({"$sort": {"file_size": -1}}) # Largest Size
                elif sort_key == "min": pipeline.append({"$sort": {"file_size": 1}})  # Smallest Size
            
            pipeline.extend([{"$skip": offset}, {"$limit": limit}])
            
            cursor = self.col.aggregate(pipeline)
            results = await cursor.to_list(length=limit)
            
            if results: return results
            
            # Agar result nahi mila, to Error raise karo fallback ke liye
            raise Exception("No fuzzy match")

        except Exception as e:
            # 2️⃣ FALLBACK: Regex Search (Backup)
            return await self.get_search_results_fallback(query, file_type, lang, quality, year, size_key, sort_key, offset, limit)

    # --- FALLBACK SEARCH - UPDATED FOR SMART REGEX 🆕 ---
    async def get_search_results_fallback(self, query, file_type, lang, quality, year, size_key, sort_key, offset, limit):
        
        # 🆕 2. CLEAN & ORDER-INDEPENDENT SEARCH
        query = standardize_tv_tags(query)
        words = query.split()
        
        # 🆕 Duplicate words hatana taaki DB par load na pade
        words = list(dict.fromkeys(words))
        
        # Har ek word ke liye alag filter, isse words aage piche hone par bhi match hoga!
        mongo_query = {"$and": []}
        
        for word in words:
            char_pattern = r"[\s\W]*".join(list(word))
            mongo_query["$and"].append({
                "$or": [
                    {"file_name": {"$regex": char_pattern, "$options": "i"}},
                    {"search_text": {"$regex": char_pattern, "$options": "i"}},
                    {"caption": {"$regex": char_pattern, "$options": "i"}}
                ]
            })

        if file_type and file_type != "None": mongo_query["$and"].append({"file_type": file_type})
        
        if size_key and size_key != "None":
            size_query = {}
            if size_key == "s": size_query = {"$lt": 524288000}
            elif size_key == "m": size_query = {"$gte": 524288000, "$lt": 1073741824}
            elif size_key == "l": size_query = {"$gte": 1073741824, "$lt": 2147483648}
            elif size_key == "xl": size_query = {"$gte": 2147483648}
            if size_query: mongo_query["$and"].append({"file_size": size_query})

        if lang and lang != "None":
             pat = LANG_PATTERNS.get(lang.capitalize())
             if pat: mongo_query["$and"].append({"$or": [{"file_name": {"$regex": pat}}, {"caption": {"$regex": pat}}]})
        
        if quality and quality != "None":
            pat = QUAL_PATTERNS.get(quality, re.compile(rf'\b{quality}\b', re.IGNORECASE))
            mongo_query["$and"].append({"file_name": {"$regex": pat}})
            
        if year and year != "None":
            mongo_query["$and"].append({"file_name": {"$regex": re.compile(rf'\b{year}\b')}})

        # Agar $and khali reh jaye to simplify karna
        if len(mongo_query["$and"]) == 0:
            mongo_query = {}
        elif len(mongo_query["$and"]) == 1:
            mongo_query = mongo_query["$and"][0]

        cursor = self.col.find(mongo_query)
        
        # --- SORTING LOGIC (CURSOR) ---
        if sort_key == "new": cursor.sort('_id', -1)
        elif sort_key == "old": cursor.sort('_id', 1)
        elif sort_key == "max": cursor.sort('file_size', -1)
        elif sort_key == "min": cursor.sort('file_size', 1)
        else: cursor.sort('_id', -1) # Default behavior

        cursor.skip(offset).limit(limit)
        return await cursor.to_list(length=limit)

    # --- YEAR DETECTION (NO CHANGE) ---
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

    # =====================================================
    # 📝 UPDATED SAVE LOGIC (DISPLAY VS SEARCH DECOUPLED) 🆕
    # =====================================================
    async def save_file(self, message):
        """
        Returns: 'saved', 'duplicate', or 'error'
        """
        try:
            file_info = get_file_details(message)
            if not file_info:
                return 'error'

            # 1. Clean File Name aur Caption (Ye Original Display Format Rakhega e.g. [E01-08])
            cleaned_file_name = clean_filename(file_info['file_name'])
            raw_caption = message.caption or ""
            cleaned_caption = clean_filename(raw_caption)

            # Check Duplicate
            if await self.col.find_one({'file_unique_id': file_info['file_unique_id']}):
                return 'duplicate'
            
            # 2. Hidden Search Text (Yahan par ranges E01 E02 E03 E04... mein expand hongi)
            display_name = re.sub(r'\s*(mkv|mp4|avi|mov|flv|wmv|zip|rar|pdf)$', '', cleaned_file_name, flags=re.IGNORECASE)
            
            # Sirf search query ke liye standardization lagayenge taaki wo accurately match ho
            search_base = standardize_tv_tags(display_name)
            spaceless_name = search_base.replace(" ", "").replace("-", "")
            master_search_text = f"{search_base} {spaceless_name}"

            doc = {
                'file_id': file_info['file_id'],
                'file_unique_id': file_info['file_unique_id'],
                'file_name': cleaned_file_name,     # 🌟 Display mein E01-08 dikhega
                'search_text': master_search_text,  # 🌟 Par Search Engine mein E01 E02 aayega
                'file_size': file_info['file_size'],
                'file_type': file_info['file_type'],
                'mime_type': file_info['mime_type'],
                'caption': cleaned_caption,         # 🌟 Caption mein bhi E01-08 dikhega
                'chat_id': message.chat.id,
                'message_id': message.id,
                'link_id': generate_link_id()
            }
            await self.col.insert_one(doc)
            return 'saved'
        except Exception as e:
            logger.error(f"Save Error: {e}")
            return 'error'

    # --- UTILS (NO CHANGE) ---
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
