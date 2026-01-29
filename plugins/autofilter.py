import math
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified

# Database Imports
from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
from utils import get_size, btn_parser # Importing updated btn_parser from utils

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

# ==========================================
# 1. MAIN SEARCH HANDLER
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    
    if not query or len(query) < 2 or query.startswith("/"):
        return

    if not client.me:
        await client.get_me()

    # 🚀 Step 1: Check Group Settings (Cache)
    settings = await db_users.get_group_status(message.chat.id)

    # 🚀 Step 2: Save Query First (Essential for ID)
    search_id = await db.save_search_query(query, message.from_user.id)
    
    if not search_id:
        return await message.reply("❌ Database Error. Please try again.")

    # 🚀 Step 3: Initial Search (No Filters)
    # lang=None, quality=None, year=None, size=None
    files = await db.get_search_results(query, lang=None, quality=None, year=None, size_key=None)

    # Log Analytics
    asyncio.create_task(
        analytics.log_search(message.text, query, len(files), message.from_user.id, message.chat.id)
    )

    if not files:
        return 

    # Generate Buttons (Initial state: No filters)
    reply_markup = await btn_parser(
        search_id, files, client, offset=0, 
        active_lang=None, active_qual=None, active_year=None, active_size=None
    )

    await message.reply_text(
        text=f"🔎 **Found {len(files)} results for:** `{query}`\n👇 **Select Filters or Click to Download:**",
        reply_markup=reply_markup,
        quote=True
    )


# ==========================================
# 2. MASTER FILTER & PAGINATION HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^(next|filter)_"))
async def filter_pagination_handler(client: Client, callback: CallbackQuery):
    """
    Handles Next Page AND Filter Clicks in one robust function.
    Data Format: action_id_offset_lang_qual_year_size
    Example: next_102_10_hindi_720p_2023_l
    """
    data = callback.data.split("_")
    
    try:
        # data[0] is action (next/filter) - ignored
        search_id = int(data[1])
        offset = int(data[2])
        
        # Helper to treat "None" string as None object
        def clean(val): return None if val == "None" else val
        
        # Safe Extraction for all 4 Filters
        active_lang = clean(data[3])
        active_qual = clean(data[4])
        
        # Check length for backward compatibility (in case old buttons exist)
        active_year = clean(data[5]) if len(data) > 5 else None
        active_size = clean(data[6]) if len(data) > 6 else None
        
    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    # 1. Retrieve Original Query
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired (48h). Please type query again.", show_alert=True)

    # 2. Database Search with ALL Filters 
    # Even if offset is 0 (new filter clicked), we must query DB to get counts
    files = await db.get_search_results(
        query, 
        lang=active_lang, 
        quality=active_qual,
        year=active_year,
        size_key=active_size,
        offset=offset
    )
    
    # 3. Handle Empty Results (But keep buttons alive!)
    if not files:
        if offset > 0:
            return await callback.answer("⚠️ End of pages.", show_alert=True)
        else:
            await callback.answer("⚠️ No files found for this filter combination!", show_alert=False)
            # We continue below to render the buttons (so user can uncheck)

    # 4. Generate Updated Buttons
    new_markup = await btn_parser(
        search_id, 
        files, 
        client, 
        offset, 
        active_lang, active_qual, active_year, active_size
    )

    # 5. Build Status Text (Show Active Filters)
    status = ""
    if active_lang: status += f"🏳️ {active_lang.title()} "
    if active_qual: status += f"💿 {active_qual} "
    if active_year: status += f"📅 {active_year} "
    
    # Map size key to label for display
    sizes_map = {"s": "<500MB", "m": "500MB-1GB", "l": "1GB-2GB", "xl": ">2GB"}
    if active_size: status += f"📦 {sizes_map.get(active_size, active_size)}"
    
    if status:
        text_content = f"🔎 **Results for:** `{query}`\n⚙️ **Active Filters:** {status}"
    else:
        text_content = f"🔎 **Results for:** `{query}`"

    try:
        await callback.edit_message_text(
            text=text_content,
            reply_markup=new_markup
        )
    except MessageNotModified:
        pass
    except Exception as e:
        print(f"Update Error: {e}")


# ==========================================
# 3. PAGE COUNTER HANDLER
# ==========================================
@Client.on_callback_query(filters.regex("pages"))
async def pages_handler(_, callback):
    await callback.answer("ℹ️ This is the current page number.", show_alert=True)


# ==========================================
# 4. FILE DELIVERY HANDLER (Priority High)
# ==========================================
@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client: Client, message: Message):
    """
    Handles deep link delivery. High priority.
    """
    if len(message.command) < 2:
        return
    
    payload = message.command[1]
    
    if not payload.startswith("file_"):
        return

    try:
        link_id = payload.split("file_", 1)[1]
    except IndexError:
        return await message.reply("❌ Invalid Link Format")

    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info:
        return await message.reply("❌ File not found (Deleted or Invalid).")

    # Add User to DB
    await db_users.add_user(message.from_user.id, message.from_user.first_name)

    status_msg = await message.reply("📂 **Found File! Sending now...**")

    try:
        await client.send_cached_media(
            chat_id=message.from_user.id,
            file_id=file_info['file_id'],
            caption=file_info['caption'] or "",
        )
        await status_msg.delete()
    
    except Exception as e:
        print(f"Error Sending File: {e}")
        # If deleted from Telegram, remove from DB
        if "MEDIA_EMPTY" in str(e) or "400" in str(e):
             await db.col.delete_one({"link_id": link_id})
             await status_msg.edit("❌ **File Expired:** This file was deleted from Telegram servers.")
        else:
             await status_msg.edit(f"❌ Error sending file: {str(e)}")


# ==========================================
# 5. CLOSE HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client: Client, callback: CallbackQuery):
    await callback.message.delete()
