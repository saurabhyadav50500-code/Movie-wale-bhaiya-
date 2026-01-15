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

    async def ensure_indexes(self):
        """
        Creates the Text Index for Fuzzy & Smart Search.
        Weights determine priority: Exact Name (10) > Meta (5) > Fuzzy (3).
        """
        try:
            await self.col.create_index(
                [
                    ("file_name", "text"),
                    ("search_text", "text"),
                    ("ngram_text", "text"),  # 👈 New Fuzzy Field
                    ("caption", "text")
                ],
                weights={
                    "file_name": 10,
                    "search_text": 5,
                    "ngram_text": 3,         # 👈 Fuzzy Weight
                    "caption": 1
                },
                name="SmartFuzzyIndex"
            )
            logger.info("✅ Smart Fuzzy Index created successfully.")
        except Exception as e:
            logger.error(f"❌ Error creating index: {e}")

    # ==================================================================
    # 🧠 SMART INDEXING HELPERS
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
    def generate_ngrams(text, n=2):
        """
        Generates N-Grams (Bigrams) for Fuzzy Indexing.
        Input: "Iron" -> Output: "ir ro on"
        """
        if not text: return ""
        text = text.lower().replace(" ", "") # Remove spaces for continuity
        ngrams = [text[i:i+n] for i in range(len(text)-n+1)]
        return " ".join(ngrams)

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

        for lang in ["hindi", "english", "tamil", "telugu", "malayalam", "kannada"]:
            if lang in text: meta["languages"].add(lang)
            
        if any(k in text for k in ["multi", "dual", "org", "sub"]):
            meta["languages"].add("hindi")

        return meta

    # ==================================================================
    # 💾 DATABASE OPERATIONS
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

            # Step A: Name Swapping
            is_generic = re.match(r'^(vid|img|tg|telegram)_\d+', clean_fname) or len(clean_fname) < 5
            if is_generic and clean_cap:
                display_name = raw_cap.splitlines()[0][:100]
                primary_src = clean_cap
            else:
                display_name = raw_fname
                primary_src = clean_fname

            # Step B: Helpers
            spaceless = primary_src.replace(" ", "")
            meta = self.parse_file_details(primary_src + " " + clean_cap)
            extra_text = " ".join(list(set(clean_cap.split()) - set(primary_src.split())))

            # 🟢 Step C: FUZZY DATA (N-Grams)
            # "Iron Man" -> "ir ro on nm ma an"
            ngram_text = self.generate_ngrams(primary_src)

            # Step D: Master Search Field
            parts = [primary_src, spaceless, meta['year'], meta['quality'], 
                     " ".join(meta['languages']), " ".join(meta['episodes']), extra_text]
            final_search_text = " ".join([p for p in parts if p]).lower()

            doc = {
                'file_id': file_info['file_id'],
                'file_unique_id': file_info['file_unique_id'],
                'file_name': display_name,
                'file_size': file_info['file_size'],
                'file_type': file_info['file_type'],
                'mime_type': file_info['mime_type'],
                'caption': raw_cap,
                
                # Search Fields
                'search_text': final_search_text,
                'ngram_text': ngram_text,  # 👈 Saved for Fuzzy Search
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
        return await self.save_batch([message]) == 1

    async def get_search_results(self, query):
        """
        Searches using Text Index (Exact + Fuzzy N-Grams).
        """
        query = self.clean_text(query)
        if not query: return []

        # 1. Generate N-Grams for Query to match typos
        query_ngrams = self.generate_ngrams(query)
        
        # 2. Combine: "Query" OR "q u e r y n g r a m s"
        final_query = f"{query} {query_ngrams}"

        # 3. Aggregation for Scoring
        pipeline = [
            {"$match": {"$text": {"$search": final_query}}},
            {"$project": {
                "file_name": 1, "file_size": 1, "caption": 1, "file_id": 1, "link_id": 1,
                "score": {"$meta": "textScore"} # Sort by relevance
            }},
            {"$sort": {"score": -1}},
            {"$limit": 50}
        ]

        try:
            cursor = self.col.aggregate(pipeline)
            return await cursor.to_list(length=50)
        except Exception as e:
            logger.error(f"Search Error: {e}")
            # Fallback to simple Regex if Index fails/not exists
            return await self.col.find({"search_text": {"$regex": query, "$options": "i"}}).to_list(length=50)

    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        await self.col.delete_many({})

db = Media()
