import re
import logging
import motor.motor_asyncio
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id

logger = logging.getLogger(__name__)

class Media:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]
        # Ensure indexes are created when the class is initialized
        # Note: In production, it's often better to call this explicitly on bot startup.
    
    async def ensure_indexes(self):
        """
        Creates the Text Index with specific weights for Relevance Scoring.
        This enables the 'Smart Search' logic.
        """
        try:
            # 1. file_name (10): Highest priority. If query matches filename, it tops the list.
            # 2. search_text (5): Medium. Contains parsed metadata (year, quality, etc).
            # 3. caption (1): Low. Good for finding keywords not in the filename.
            await self.col.create_index(
                [
                    ("file_name", "text"),
                    ("search_text", "text"),
                    ("caption", "text")
                ],
                weights={
                    "file_name": 10,
                    "search_text": 5,
                    "caption": 1
                },
                name="SmartSearchIndex"
            )
            logger.info("✅ Smart Search Text Index created successfully.")
        except Exception as e:
            logger.error(f"❌ Error creating index: {e}")

    async def get_search_results(self, query, sort_mode="score"):
        """
        Relevance-Based Smart Search System.
        1. Expands query (Desi mapping).
        2. Extracts Year.
        3. Tries Text Search (Aggregation) for relevance.
        4. Falls back to Regex (Split Word) if no results found.
        """
        query = query.lower().strip()
        if not query:
            return []

        # =========================================================
        # 🟢 STEP 1: QUERY EXPANSION (Language & Desi Mapping)
        # =========================================================
        
        # 1. Language Map
        lang_map = {
            'hin': 'hindi', 'tam': 'tamil', 'tel': 'telugu', 
            'mal': 'malayalam', 'kan': 'kannada', 'eng': 'english',
            'jap': 'japanese', 'kor': 'korean', 'chn': 'chinese'
        }
        
        # 2. Desi (Hinglish) Map
        desi_map = {
            'seas': 'season', 'ep': 'episode', 
            'part': 'pt', 'vol': 'volume', 
            'mov': 'movie', 'nat': 'nature',
            'doc': 'documentary'
        }

        words = query.split()
        expanded_words = set(words) # Use set to avoid duplicates

        for word in words:
            # Check Language Map
            if word in lang_map:
                expanded_words.add(lang_map[word])
            
            # Check Desi Map
            if word in desi_map:
                expanded_words.add(desi_map[word])

        # Reconstruct the query string with added keywords
        expanded_query = " ".join(expanded_words)

        # =========================================================
        # 🟢 STEP 2: SMART YEAR EXTRACTION
        # =========================================================
        
        filter_year = None
        # Regex to find a year between 1900 and 2099
        year_match = re.search(r'\b(19|20)\d{2}\b', expanded_query)
        
        if year_match:
            filter_year = year_match.group(0)
            # Remove year from text query so it doesn't mess up text relevance
            # (We will use it as a strict filter instead)
            expanded_query = expanded_query.replace(filter_year, "").strip()

        # =========================================================
        # 🟢 STEP 3: PRIMARY SEARCH (Aggregation Pipeline)
        # =========================================================
        
        # Build the Match Stage
        match_stage = {
            "$text": {"$search": expanded_query}
        }

        # Apply Strict Year Filter if found
        if filter_year:
            # We search inside 'search_text' because that contains the parsed year
            match_stage["search_text"] = {"$regex": filter_year}

        pipeline = [
            {"$match": match_stage},
            # Score: Project relevance score based on Text Weights
            {"$project": {
                "file_name": 1, "file_size": 1, "caption": 1, "file_id": 1, 
                "link_id": 1, "search_text": 1,
                "score": {"$meta": "textScore"}
            }},
            # Sort by Score (High to Low)
            {"$sort": {"score": -1}},
            {"$limit": 50}
        ]

        try:
            cursor = self.col.aggregate(pipeline)
            results = await cursor.to_list(length=50)
            
            if results:
                return results
                
        except Exception as e:
            logger.error(f"Error in Aggregation: {e}")

        # =========================================================
        # 🟢 STEP 4: REGEX FALLBACK (Split Word Logic)
        # =========================================================
        # If Text Search failed (e.g., partial words, typos), try Regex.
        
        # Split original query (without year) into words
        raw_words = query.replace(filter_year, "") if filter_year else query
        split_words = raw_words.split()
        
        if not split_words:
            return []

        # Create OR Pattern: (Word1|Word2|Word3)
        # Using re.escape to handle symbols safely
        regex_pattern = "|".join([re.escape(w) for w in split_words if len(w) > 2])
        
        if not regex_pattern:
            return []

        # Construct Filter
        regex_filter = {"$regex": regex_pattern, "$options": "i"}
        
        fallback_query = {
            "$or": [
                {"file_name": regex_filter},
                {"search_text": regex_filter}
            ]
        }

        # Strict Year Filter for Fallback too
        if filter_year:
            fallback_query["search_text"] = {"$regex": filter_year}

        # Simple Find for Fallback (No scoring, usually sorts by insertion or natural order)
        cursor = self.col.find(fallback_query).limit(50)
        return await cursor.to_list(length=50)

    # ... (Keep existing methods: save_file, save_batch, get_file_by_link_id, delete_all_files) ...
    
    async def save_file(self, media_message):
        # ... (Previous Logic) ...
        # Ensure you include save_batch logic provided in previous response here
        pass
        
    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        await self.col.delete_many({})

db = Media()
