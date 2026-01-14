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

    # ==================================================================
    # 🧠 SMART INDEXING HELPERS (Clean, Parse, Analyze)
    # ==================================================================

    @staticmethod
    def clean_text(text):
        """
        Advanced cleaning: Removes extensions, dots, usernames, links.
        Converts Roman Numerals (I-V) to Digits.
        """
        if not text:
            return ""

        text = text.lower()

        # 1. Remove File Extension (e.g., .mkv, .mp4 at the end)
        text = re.sub(r'\.[a-z0-9]{2,5}$', '', text)

        # 2. Remove Usernames (@user) and Links (http/www)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'https?://\S+|www\.\S+', '', text)

        # 3. Replace Dots, Underscores, Brackets with Spaces
        text = re.sub(r'[._\-\[\]\(\)\{\}]', ' ', text)

        # 4. Roman Numeral Fix (I, II, III, IV, V) -> (1, 2, 3, 4, 5)
        # Using word boundaries (\b) to ensure we don't change "LIVE" to "L4E"
        roman_map = {
            r'\bi\b': ' 1 ',
            r'\bii\b': ' 2 ',
            r'\biii\b': ' 3 ',
            r'\biv\b': ' 4 ',
            r'\bv\b': ' 5 '
        }
        for pattern, replacement in roman_map.items():
            text = re.sub(pattern, replacement, text)

        # 5. Cleanup excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def parse_file_details(text):
        """
        Extracts metadata: Year, Quality, Episodes, Languages.
        Handles Multi-Audio logic.
        """
        text = text.lower()
        meta = {
            "quality": "",
            "year": "",
            "languages": set(),
            "episodes": set()
        }

        # --- A. Quality & Year ---
        # Match 480p, 720p, 1080p, 2160p, 4k
        qualities = re.findall(r'\b(480p|720p|1080p|2160p|4k)\b', text)
        if qualities:
            meta["quality"] = qualities[0]

        # Match Year (1990-2029)
        years = re.findall(r'\b(19\d{2}|20[0-2]\d)\b', text)
        if years:
            meta["year"] = years[0]

        # --- B. Episode Expansion ---
        # Matches S01E01, S1E1, S1 E1
        ep_match = re.search(r'\bs(\d+)\s*e(\d+)\b', text)
        if ep_match:
            season, episode = ep_match.groups()
            # Generate variations for search: "s01e01", "e1", "episode 1"
            meta["episodes"].add(f"s{season}e{episode}")
            meta["episodes"].add(f"e{int(episode)}")
            meta["episodes"].add(f"episode {int(episode)}")
            meta["episodes"].add(f"season {int(season)}")

        # --- C. Language & Multi-Audio ---
        common_langs = [
            "hindi", "english", "tamil", "telugu", "malayalam", 
            "kannada", "bengali", "punjabi", "marathi", "gujarati"
        ]
        
        for lang in common_langs:
            if lang in text:
                meta["languages"].add(lang)

        # Smart Logic: If Multi/Dual/Org/Sub found, but Hindi not found -> Add Hindi
        # (Assuming target audience is Indian users mostly)
        keywords = ["multi", "dual", "org", "sub"]
        if any(k in text for k in keywords):
            meta["languages"].add("hindi") # Implicitly add Hindi for Dual Audio

        return meta

    # ==================================================================
    # 💾 DATABASE OPERATIONS (Save Batch & Search)
    # ==================================================================

    async def save_batch(self, messages):
        """
        Process a list of Pyrogram Messages, apply intelligent indexing, 
        and save to MongoDB using bulk write.
        """
        documents = []

        for message in messages:
            # 1. Basic Extraction
            file_info = get_file_details(message)
            if not file_info:
                continue

            # Original raw strings
            raw_filename = file_info['file_name'] or ""
            raw_caption = message.caption or ""

            # 2. Clean Texts
            clean_fname = self.clean_text(raw_filename)
            clean_cap = self.clean_text(raw_caption)

            # --- STEP A: NAME SWAPPING (Display Logic) ---
            # If filename is junk (VID_..., IMG_..., or too short), use Caption
            is_generic = re.match(r'^(vid|img|tg|telegram)_\d+', clean_fname) or len(clean_fname) < 5
            
            if is_generic and clean_cap:
                display_name = raw_caption.splitlines()[0][:100] # Use first line of caption
                primary_search_source = clean_cap
            else:
                display_name = raw_filename
                primary_search_source = clean_fname

            # --- STEP B: SPACELESS GENERATION ---
            spaceless_name = primary_search_source.replace(" ", "")

            # --- STEP C: SMART MERGE (Caption Analysis) ---
            # Find words in caption that are NOT in filename
            fname_words = set(primary_search_source.split())
            cap_words = set(clean_cap.split())
            extra_keywords = list(cap_words - fname_words)
            extra_text = " ".join(extra_keywords)

            # --- STEP D: METADATA PARSING ---
            # Extract Years, Quality, Language from the richest source
            meta = self.parse_file_details(primary_search_source + " " + clean_cap)
            
            # --- STEP E: MASTER SEARCH FIELD CONSTRUCTION ---
            # Combine everything into one super-searchable string
            search_text_parts = [
                primary_search_source,      # Main Name (Cleaned)
                spaceless_name,             # Spaceless version
                meta['year'],               # 2024
                meta['quality'],            # 1080p
                " ".join(meta['languages']),# hindi english
                " ".join(meta['episodes']), # s01e01 e1
                extra_text                  # Unique words from caption
            ]
            
            # Join and remove duplicate spaces
            final_search_text = " ".join([p for p in search_text_parts if p]).lower()

            # Generate IDs
            link_id = generate_link_id()

            # Create Document
            doc = {
                'file_id': file_info['file_id'],
                'file_unique_id': file_info['file_unique_id'],
                'file_name': display_name,  # Shows in Buttons
                'file_size': file_info['file_size'],
                'file_type': file_info['file_type'],
                'mime_type': file_info['mime_type'],
                'caption': raw_caption,     # Original Caption for sending
                
                # Indexing Fields
                'search_text': final_search_text, # The Brain 🧠
                'chat_id': message.chat.id,
                'message_id': message.id,
                'link_id': link_id
            }
            documents.append(doc)

        # Bulk Insert (Ordered=False to ignore duplicates and continue)
        if documents:
            try:
                await self.col.insert_many(documents, ordered=False)
                return len(documents)
            except motor.motor_asyncio.AsyncIOMotorerrors.BulkWriteError as e:
                # Return count of successfully inserted documents
                return e.details.get('nInserted', 0)
        return 0

    async def save_file(self, message):
        """Wrapper for saving a single file using the batch logic."""
        result = await self.save_batch([message])
        return result == 1

    async def get_search_results(self, query):
        """
        Search using the new 'search_text' field.
        """
        # Clean the user's query first (convert roman, remove dots)
        cleaned_query = self.clean_text(query)
        regex = {"$regex": cleaned_query, "$options": "i"}

        # Search specifically in the Master Search Field
        cursor = self.col.find({"search_text": regex})
        return await cursor.to_list(length=100)

    async def get_file_by_link_id(self, link_id):
        return await self.col.find_one({"link_id": link_id})

    async def delete_all_files(self):
        await self.col.delete_many({})

db = Media()
