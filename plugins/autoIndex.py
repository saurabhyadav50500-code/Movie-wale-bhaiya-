import logging
from pyrogram import Client, filters
from database.ia_filterdb import db

# Logger setup (Console me dikhane ke liye)
logger = logging.getLogger(__name__)

# --- LIVE AUTO INDEXING ---
# Ye function tab chalega jab Channel me Nayi File aayegi
@Client.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def auto_index_post(bot, message):
    """
    Catch new files uploaded to any channel where Bot is Admin 
    and save them to Database automatically.
    """
    try:
        # File Database me save karein
        is_saved = await db.save_file(message)
        
        if is_saved:
            print(f"✅ New File Indexed: {message.document.file_name if message.document else 'Video/Audio'}")
        else:
            print(f"♻️ Duplicate File (Already Exists): {message.id}")
            
    except Exception as e:
        logger.error(f"❌ Error in Auto Indexing: {e}")
