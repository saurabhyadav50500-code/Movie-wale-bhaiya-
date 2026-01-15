import re
import logging
import motor.motor_asyncio
from datetime import datetime
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id

logger = logging.getLogger(__name__)

class Media:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]
        
        # 👇 NEW: Pagination Fix Collections
        self.temp_col = self.db["temp_searches"]  # Stores query text temporarily
        self.seq_col = self.db["sequences"]       # Generates IDs (1, 2, 3...)

    async def ensure_indexes(self):
        """
        Creates standard indexes and TTL index for temp searches.
        Note: Fuzzy Index is managed via MongoDB Atlas Website.
        """
        try:
            # 1. Standard File Indexes
            await self.col.create_index("file_unique_id", unique=True)
            await self.col.create_index("link_id")
            # Fallback text index (just in case)
            await self.col.create_index([("file_name", "text")])
            
            # 2. 👇 NEW: TTL Index (Delete temp searches after 48 hours)
            # 172800 seconds = 48 Hours
            await self.temp_col.create_index("created_at", expireAfterSeconds=172800)
            
            logger.info("✅ Database Indexes Created Successfully.")
        except Exception as e:
            logger.error(f"❌ Error creating index: {e}")

    # ==================================================================
    # 🔢 PAGINATION & ID GENERATION (Fix for Button Data Too Long)
    # ==================================================================

    async def get_next_sequence(self):
        """Generates a unique incremental ID (1, 2, 3...) for searches."""
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
        """
        Saves the long query text mapped to a short Integer ID.
        """
        try:
            # 1. Get unique Short ID
            search_id = await self.get_next_sequence()
            
            if not search_id:
                return None

            # 2. Save using upsert=True to prevent Duplicate Key Errors
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
        """Retrieves the original text query using the Integer ID."""
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
        """Standard cleaning: Remove extensions, symbols, roman numerals."""
        if not text: return ""
        text = text.lower()
        text = re.sub(r'\.[a-z0-9]{2,5}$', '', text) # Remove extension
        text = re.sub(r'@\w+', '', text) # Remove username
        text = re.sub(r'https?://\S+|www\.\S+', '', text) # Remove links
        text = re.sub(r'[._\-\[\]\(\)\{\}]', ' ', text) # Remove symbols
        
        # Roman Numeral Fix (I -> 1, II -> 2)
        roman_map = {r'\bi\b': ' 1 ', r'\bii\b': ' 2 ', r'\biii\b': ' 3 ', r'\biv\b': ' 4 ', r'\bv\b': ' 5 '}
        for pattern, replacement in roman_map.items():
            text = re.sub(pattern, replacement, text)
            
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def parse_file_details(text):
        """Extracts Year, Quality, Episodes, Languages."""
        text = text.lower()
        meta = {"quality": "", "year": "", "languages": set(), "episodes": set()}
        
        # Quality & Year
        qualities = re.findall(r'\b(480p|720p|1080p|2160p|4k)\b', text)
        if qualities: meta["quality"] = qualities[0]
        
        years = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', text)
        if years: meta["year"] = years[0]

        # Episodes
        ep_match = re.search(r'\bs(\d+)\s*e(\d+)\b', text)
        if ep_match:
            s, e = ep_match.groups()
            meta["episodes"].update([f"s{s}e{e}", f"e{int(e)}", f"episode {int(e)}"])

        # Languages
        common_langs = ["hindi", "english", "tamil", "telugu", "malayalam", "kannada", "bengali"]
        for lang in common_langs:
            if lang in text: meta["languages"].add(lang)
            
        if any(k in text for k in ["multi", "dual", "org", "sub"]):
            meta["languages"].add("hindi")

        return meta

    # ==================================================================
    # 💾 DATABASE OPERATIONS (Save Batch)
    # ==================================================================

    async def save_batch(self, messages):
        """
        Saves a list of messages. No heavy N-Grams needed (handled by Atlas).
        """
        documents = []
        for message in messages:
            file_info = get_file_details(message)
            if not file_info: continue

            raw_fname = file_info['file_name'] or ""
            raw_cap = message.caption or ""
            
            clean_fname = self.clean_text(raw_fname)
            clean_cap = self.clean_text(raw_cap)

            # Name Swapping logic
            is_generic = re.match(r'^(vid|img|tg|telegram)_\d+', clean_fname) or len(clean_fname) < 5
            if is_generic and clean_cap:
                display_name = raw_cap.splitlines()[0][:100]
            else:
                display_name = raw_fname

            # Construct Document
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
                # Ordered=False ensures if one fails (duplicate), others still save
                await self.col.insert_many(documents, ordered=False)
                return len(documents)
            except motor.motor_asyncio.AsyncIOMotorerrors.BulkWriteError as e:
                return e.details.get('nInserted', 0)
        return 0

    async def save_file(self, message):
        result = await self.save_batch([message])
        return result == 1

    # ==================================================================
    # 🔎 SEARCH LOGIC (Atlas Fuzzy Search)
    # ==================================================================

    async def get_search_results(self, query):
        """
        Priority 1: MongoDB Atlas Fuzzy Search (Handling Typos)
        Priority 2: Fallback to Regex (If Atlas fails or matches nothing)
        """
        if not query: return []
        
        query = self.clean_text(query)

        # --- 1. ATLAS SEARCH PIPELINE ---
        pipeline = [
            {
                "$search": {
                    "index": "default", # Must match Index Name on Website
                    "compound": {
                        "should": [
                            {
                                "autocomplete": {
                                    "query": query,
                                    "path": "file_name",
                                    "fuzzy": {"maxEdits": 2}, # Handles 2 typos
                                    "score": {"boost": {"value": 3}} # Filename match is priority
                                }
                            },
                            {
                                "text": {
                                    "query": query,
                                    "path": "caption",
                                    "fuzzy": {"maxEdits": 1}
                                }
                            }
                        ]
                    }
                }
            },
            {
                "$limit": 50
            },
            {
                "$project": {
                    "file_name": 1, 
                    "file_size": 1, 
                    "caption": 1, 
                    "file_id": 1, 
                    "link_id": 1, 
                    "score": {"$meta": "searchScore"}
                }
            }
        ]

        try:
            cursor = self.col.aggregate(pipeline)
            results = await cursor.to_list(length=50)
            if results: 
                return results
        except Exception as e:
            logger.error(f"⚠️ Atlas Search Error (Check Index): {e}")

        # --- 2. FALLBACK (Regex) ---
        return await self.get_search_results_fallback(query)

    async def get_search_results_fallback(self, query):
        """
        Fallback method using standard Regex if Atlas fails.
        """
        split_words = query.split()
        if not split_words: return []

        # Only use words longer than 2 chars for regex
        valid_words = [re.escape(w) for w in split_words if len(w) > 2]
        if not valid_words: return []

        regex_pattern = "|".join(valid_words)
        
        regex_query = {
            "$or": [
                {"file_name": {"$regex": regex_pattern, "$options": "i"}},
                {"caption": {"$regex": regex_pattern, "$options": "i"}}
            ]
        }
        
        return await self.col.find(regex_query).limit(50).to_list(length=50)

    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        """Force drops collection."""
        await self.col.drop()

db = Media()
