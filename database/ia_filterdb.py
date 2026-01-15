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
        Creates the Text Index with weights for Relevance & Fuzzy Scoring.
        """
        try:
            # Create Text Index
            # Weights: 
            # 10 -> Exact Name (Highest)
            # 5  -> Metadata (Medium)
            # 3  -> Fuzzy N-Grams (Typo Tolerance)
            # 1  -> Caption (Low)
            await self.col.create_index(
                [
                    ("file_name", "text"),
                    ("search_text", "text"),
                    ("ngram_text", "text"),  # 👈 Fuzzy Field
                    ("caption", "text")
                ],
                weights={
                    "file_name": 10,
                    "search_text": 5,
                    "ngram_text": 3,
                    "caption": 1
                },
                name="SmartFuzzyIndex"
            )
            logger.info("✅ Smart Fuzzy Index created successfully.")
        except Exception as e:
            logger.error(f"❌ Error creating index: {e}")

    # ==================================================================
    # 🧠 SMART INDEXING HELPERS (Clean, Parse, Fuzzy)
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
    def generate_ngrams(text, n=2):
        """
        Generates N-Grams (Bigrams) for Fuzzy Indexing.
        Input: "Iron" -> Output: "ir ro on"
        """
        if not text: return ""
        # Remove spaces to fuzzy match across words
        text = text.lower().replace(" ", "")
        # Generate sliding window of 2 characters
        ngrams = [text[i:i+n] for i in range(len(text)-n+1)]
        return " ".join(ngrams)

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
        Saves a list of messages with Fuzzy & Smart Metadata.
        """
        documents = []
        for message in messages:
            file_info = get_file_details(message)
            if not file_info: continue

            raw_fname = file_info['file_name'] or ""
            raw_cap = message.caption or ""
            
            clean_fname = self.clean_text(raw_fname)
            clean_cap = self.clean_text(raw_cap)

            # Step A: Name Swapping (Use caption if filename is generic)
            is_generic = re.match(r'^(vid|img|tg|telegram)_\d+', clean_fname) or len(clean_fname) < 5
            if is_generic and clean_cap:
                display_name = raw_cap.splitlines()[0][:100]
                primary_src = clean_cap
            else:
                display_name = raw_fname
                primary_src = clean_fname

            # Step B: Prepare Search Data
            spaceless = primary_src.replace(" ", "")
            meta = self.parse_file_details(primary_src + " " + clean_cap)
            extra_text = " ".join(list(set(clean_cap.split()) - set(primary_src.split())))

            # 🟢 Step C: FUZZY DATA GENERATION
            # "Iron Man" -> "ir ro on nm ma an"
            ngram_text = self.generate_ngrams(primary_src)

            # Step D: Construct Master Search Field
            parts = [
                primary_src, 
                spaceless, 
                meta['year'], 
                meta['quality'], 
                " ".join(meta['languages']), 
                " ".join(meta['episodes']), 
                extra_text
            ]
            final_search_text = " ".join([p for p in parts if p]).lower()

            # Create Document
            doc = {
                'file_id': file_info['file_id'],
                'file_unique_id': file_info['file_unique_id'],
                'file_name': display_name,
                'file_size': file_info['file_size'],
                'file_type': file_info['file_type'],
                'mime_type': file_info['mime_type'],
                'caption': raw_cap,
                
                # Indexing Fields
                'search_text': final_search_text,
                'ngram_text': ngram_text,  # 👈 Crucial for Fuzz
                
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
    # 🔎 SEARCH LOGIC (Text + Fuzzy + Fallback)
    # ==================================================================

    async def get_search_results(self, query):
        """
        1. Expands Query (Lang/Desi).
        2. Extracts Year.
        3. Generates Query N-Grams (Fuzzy).
        4. Runs Aggregation (Smart Scoring).
        5. Falls back to Regex if needed.
        """
        query = self.clean_text(query)
        if not query: return []

        # 1. Query Expansion
        lang_map = {'hin': 'hindi', 'tam': 'tamil', 'eng': 'english', 'tel': 'telugu'}
        desi_map = {'seas': 'season', 'ep': 'episode', 'mov': 'movie'}
        
        words = query.split()
        expanded_words = set(words)
        for word in words:
            if word in lang_map: expanded_words.add(lang_map[word])
            if word in desi_map: expanded_words.add(desi_map[word])
        
        expanded_query = " ".join(expanded_words)

        # 2. Year Extraction
        filter_year = None
        year_match = re.search(r'\b(19|20)\d{2}\b', expanded_query)
        if year_match:
            filter_year = year_match.group(0)
            # Remove year from text query to allow fuzzy matching on name
            expanded_query = expanded_query.replace(filter_year, "").strip()

        # 3. Generate N-Grams for Query (For Fuzzy Match)
        # This allows "Spidr" to match "Spider" via N-Grams
        query_ngrams = self.generate_ngrams(expanded_query)
        
        # Combine: "Query" OR "Ngrams"
        final_query = f"{expanded_query} {query_ngrams}"

        # 4. Aggregation Pipeline
        match_stage = {"$text": {"$search": final_query}}
        
        if filter_year:
            match_stage["search_text"] = {"$regex": filter_year}

        pipeline = [
            {"$match": match_stage},
            {"$project": {
                "file_name": 1, "file_size": 1, "caption": 1, "file_id": 1, 
                "link_id": 1, 
                "score": {"$meta": "textScore"} # Relevance Score
            }},
            {"$sort": {"score": -1}}, # High Score First
            {"$limit": 50}
        ]

        try:
            cursor = self.col.aggregate(pipeline)
            results = await cursor.to_list(length=50)
            if results: return results
        except Exception as e:
            logger.error(f"Aggregation Error: {e}")

        # 5. Fallback: Split Regex (If Fuzzy/Text fails)
        raw_words = query.replace(filter_year, "") if filter_year else query
        split_words = raw_words.split()
        if not split_words: return []

        regex_pattern = "|".join([re.escape(w) for w in split_words if len(w) > 2])
        if not regex_pattern: return []

        fallback_query = {
            "$or": [
                {"file_name": {"$regex": regex_pattern, "$options": "i"}},
                {"search_text": {"$regex": regex_pattern, "$options": "i"}}
            ]
        }
        if filter_year: fallback_query["search_text"] = {"$regex": filter_year}

        cursor = self.col.find(fallback_query).limit(50)
        return await cursor.to_list(length=50)

    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        """Force drops collection to reset indexes/data."""
        await self.col.drop()

db = Media()
