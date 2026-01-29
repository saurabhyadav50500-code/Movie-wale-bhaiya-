import re
import logging
import motor.motor_asyncio
from datetime import datetime
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id, LANG_PATTERNS, QUAL_PATTERNS

logger = logging.getLogger(__name__)

class Media:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]
        
        # Pagination & Temp Collections
        self.temp_col = self.db["temp_searches"] 
        self.seq_col = self.db["sequences"]       

    # ==================================================================
    # 🛠️ AUTO-FIX & INDEXES (Duplicate Fix + Indexing)
    # ==================================================================

    async def remove_duplicates(self):
        """Finds and deletes duplicate files to fix E11000 error."""
        logger.info("♻️ Detecting Duplicates to fix Database...")
        
        pipeline = [
            {"$group": {
                "_id": "$file_unique_id",
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {
                "count": {"$gt": 1}
            }}
        ]
        
        cursor = self.col.aggregate(pipeline)
        deleted_count = 0
        
        async for doc in cursor:
            # Keep the first one, delete the rest
            ids_to_delete = doc['ids'][1:]
            if ids_to_delete:
                await self.col.delete_many({"_id": {"$in": ids_to_delete}})
                deleted_count += len(ids_to_delete)
        
        logger.info(f"✅ Auto-Cleaned: Deleted {deleted_count} duplicate files.")

    async def ensure_indexes(self):
        """
        Smart Index Creator: Matches Duplicates -> Deletes Them -> Retries
        """
        try:
            # 1. Standard File Indexes
            await self.col.create_index("file_unique_id", unique=True)
            await self.col.create_index("link_id")
            await self.col.create_index([("file_name", "text")])
            
            # 2. TTL Index (Temp Search - 48 Hours)
            await self.temp_col.create_index("created_at", expireAfterSeconds=172800)
            
            logger.info("✅ Database Indexes Created Successfully.")
            
        except Exception as e:
            # Agar Duplicate Error (E11000) aaya to Auto-Fix chalao
            if "E11000" in str(e):
                logger.warning("⚠️ Duplicates Found! Starting Auto-Cleanup...")
                await self.remove_duplicates()
                
                # Cleanup ke baad dobara try karo
                logger.info("🔄 Retrying Index Creation...")
                try:
                    await self.col.create_index("file_unique_id", unique=True)
                    logger.info("✅ Index Created after Cleanup!")
                except Exception as e2:
                    logger.error(f"❌ Still Failing: {e2}")
            else:
                logger.error(f"❌ Error creating index: {e}")

    # ==================================================================
    # 🔢 PAGINATION & ID GENERATION
    # ==================================================================

    async def get_next_sequence(self):
        try:
            doc = await self.seq_col.find_one_and_update(
                {"_id": "search_id"},
                {"$inc": {"seq": 1}},
                upsert=True,
                return_document=True
            )
            return doc["seq"]
        except Exception as e:
            logger.error(f"Sequence Error: {e}")
            return None

    async def save_search_query(self, query, user_id):
        try:
            search_id = await self.get_next_sequence()
            if not search_id: return None

            await self.temp_col.update_one(
                {"_id": search_id}, 
                {"$set": {
                    "query": query,
                    "user_id": user_id,
                    "created_at": datetime.utcnow()
                }},
                upsert=True 
            )
            return search_id
        except Exception as e:
            logger.error(f"Save Search Error: {e}")
            return None

    async def get_search_query(self, search_id):
        try:
            doc = await self.temp_col.find_one({"_id": int(search_id)})
            return doc["query"] if doc else None
        except Exception as e:
            logger.error(f"Get Query Error: {e}")
            return None

    # ==================================================================
    # 🧹 CLEANING & PARSING HELPERS
    # ==================================================================

    @staticmethod
    def clean_text(text):
        if not text: return ""
        text = text.lower()
        text = re.sub(r'\.[a-z0-9]{2,5}$', '', text)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'https?://\S+|www\.\S+', '', text)
        text = re.sub(r'[._\-\[\]\(\)\{\}]', ' ', text)
        roman_map = {r'\bi\b': ' 1 ', r'\bii\b': ' 2 ', r'\biii\b': ' 3 ', r'\biv\b': ' 4 ', r'\bv\b': ' 5 '}
        for pattern, replacement in roman_map.items():
            text = re.sub(pattern, replacement, text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def parse_file_details(text):
        text = text.lower()
        meta = {"quality": "", "year": "", "languages": set(), "episodes": set()}
        qualities = re.findall(r'\b(480p|720p|1080p|2160p|4k)\b', text)
        if qualities: meta["quality"] = qualities[0]
        years = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', text)
        if years: meta["year"] = years[0]
        ep_match = re.search(r'\bs(\d+)\s*e(\d+)\b', text)
        if ep_match:
            s, e = ep_match.groups()
            meta["episodes"].update([f"s{s}e{e}", f"e{int(e)}", f"episode {int(e)}"])
        common_langs = ["hindi", "english", "tamil", "telugu", "malayalam", "kannada", "bengali"]
        for lang in common_langs:
            if lang in text: meta["languages"].add(lang)
        if any(k in text for k in ["multi", "dual", "org", "sub"]):
            meta["languages"].add("hindi")
        return meta

    # ==================================================================
    # 💾 DATABASE OPERATIONS (Save Logic)
    # ==================================================================

    async def save_batch(self, messages):
        documents = []
        for message in messages:
            file_info = get_file_details(message)
            if not file_info: continue

            raw_fname = file_info['file_name'] or ""
            raw_cap = message.caption or ""
            clean_fname = self.clean_text(raw_fname)
            clean_cap = self.clean_text(raw_cap)

            is_generic = re.match(r'^(vid|img|tg|telegram)_\d+', clean_fname) or len(clean_fname) < 5
            if is_generic and clean_cap:
                display_name = raw_cap.splitlines()[0][:100]
            else:
                display_name = raw_fname

            doc = {
                'file_id': file_info['file_id'],
                'file_unique_id': file_info['file_unique_id'],
                'file_name': display_name,
                'file_size': file_info['file_size'],
                'file_type': file_info['file_type'],
                'mime_type': file_info['mime_type'],
                'caption': raw_cap,
                'chat_id': message.chat.id,
                'message_id': message.id,
                'link_id': generate_link_id()
            }
            documents.append(doc)

        if documents:
            try:
                await self.col.insert_many(documents, ordered=False)
                return len(documents)
            except motor.motor_asyncio.AsyncIOMotorerrors.BulkWriteError as e:
                return e.details.get('nInserted', 0)
        return 0

    async def save_file(self, message):
        result = await self.save_batch([message])
        return result == 1

    # ==================================================================
    # 🔎 UPDATED SEARCH LOGIC (Filters + Fallback)
    # ==================================================================

    async def get_search_results(self, query, lang=None, quality=None, offset=0, limit=10):
        """
        Searches for files using Regex with optional Language & Quality filters.
        """
        if not query: return []
        
        # 1. Base Query (Match Text)
        regex_query = re.escape(query)
        words = query.split()
        if len(words) > 1:
            # Matches all words in any order
            regex_query = "".join(f"(?=.*{re.escape(w)})" for w in words)
        
        mongo_query = {
            "file_name": {"$regex": regex_query, "$options": "i"}
        }

        # 2. Add Smart Language Filter
        if lang and lang != "None":
            key = lang.capitalize()
            if key in LANG_PATTERNS:
                pattern = LANG_PATTERNS[key]
                # Filter: File Name OR Caption must contain the language pattern
                mongo_query["$and"] = [
                    {"$or": [
                        {"file_name": {"$regex": pattern}},
                        {"caption": {"$regex": pattern}}
                    ]}
                ]

        # 3. Add Smart Quality Filter
        if quality and quality != "None":
            if quality in QUAL_PATTERNS:
                pattern = QUAL_PATTERNS[quality]
            else:
                pattern = re.compile(rf'\b{quality}\b', re.IGNORECASE)

            if "$and" not in mongo_query:
                mongo_query["$and"] = []
            
            mongo_query["$and"].append(
                {"file_name": {"$regex": pattern}}
            )

        # 4. Fetch Results
        try:
            cursor = self.col.find(mongo_query)
            cursor.sort('_id', -1)  # Sort by newest
            cursor.skip(offset).limit(limit)
            
            files = await cursor.to_list(length=limit)
            return files
            
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return []

    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        """
        Deletes all documents in the collection but keeps the Index Config.
        """
        await self.col.delete_many({})

db = Media()
