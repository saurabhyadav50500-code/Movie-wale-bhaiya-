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
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

# ==========================================
# 🛠️ HELPER: BUTTON PARSER (Smart UI)
# ==========================================
async def btn_parser(search_id, files, client, offset=0, active_lang=None, active_qual=None):
    """
    Generates buttons with Smart Language & Quality Filters.
    Callback Format: next_{search_id}_{offset}_{lang}_{qual}
    """
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []
    
    # 1. FILE BUTTONS
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot"

    if not current_files and offset == 0:
        # ⚠️ ZERO RESULTS HANDLING: Show dummy button so filters don't vanish
        buttons.append([InlineKeyboardButton("🤷‍♂️ No results with these filters", callback_data="none")])
    else:
        for file in current_files:
            f_id = file.get('link_id') 
            f_name = file.get('file_name', 'Unknown File')
            f_size = get_size(file.get('file_size', 0))
            
            if len(f_name) > 30:
                f_name = f_name[:27] + "..."
                
            buttons.append(
                [InlineKeyboardButton(
                    text=f"📂 {f_name} | {f_size}",
                    url=f"https://t.me/{bot_username}?start=file_{f_id}"
                )]
            )

    # 2. FILTER ROW 1: LANGUAGES
    # Logic: Toggle "✅" if selected. Keep Quality state unchanged.
    lang_row = []
    langs = ["Hindi", "English", "Tamil", "Telugu"] # You can add more
    
    for lang in langs:
        lang_code = lang.lower()
        
        # If active, show Checkmark and allow unchecking (set to 'None')
        if active_lang == lang_code:
            text = f"✅ {lang}"
            next_lang = "None"
        else:
            text = lang
            next_lang = lang_code
            
        # Data: filter_{id}_{offset}_{lang}_{qual}
        # We use offset=0 because changing filter resets page to 1
        current_qual_safe = active_qual if active_qual else "None"
        cb_data = f"filter_{search_id}_0_{next_lang}_{current_qual_safe}"
        
        lang_row.append(InlineKeyboardButton(text, callback_data=cb_data))
    
    buttons.append(lang_row)

    # 3. FILTER ROW 2: QUALITIES
    # Logic: Toggle "✅" if selected. Keep Language state unchanged.
    qual_row = []
    quals = ["480p", "720p", "1080p"]
    
    for qual in quals:
        qual_code = qual.lower()
        
        if active_qual == qual_code:
            text = f"✅ {qual}"
            next_qual = "None"
        else:
            text = qual
            next_qual = qual_code
            
        current_lang_safe = active_lang if active_lang else "None"
        cb_data = f"filter_{search_id}_0_{current_lang_safe}_{next_qual}"
        
        qual_row.append(InlineKeyboardButton(text, callback_data=cb_data))

    buttons.append(qual_row)

    # 4. PAGINATION BUTTONS
    # Format: next_{id}_{offset}_{lang}_{qual}
    
    total_files = len(files)
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []
    
    # Safe strings for callback
    cb_lang = active_lang if active_lang else "None"
    cb_qual = active_qual if active_qual else "None"

    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data=f"next_{search_id}_{offset - BUTTONS_PER_PAGE}_{cb_lang}_{cb_qual}"
            )
        )

    nav_buttons.append(
        InlineKeyboardButton(
            text=f"Page {current_page}/{total_pages}",
            callback_data="pages" 
        )
    )

    if end_index < total_files:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"next_{search_id}_{end_index}_{cb_lang}_{cb_qual}"
            )
        )

    buttons.append(nav_buttons)

    # Close Button
    buttons.append([
        InlineKeyboardButton(
            text="♻️ Close / Wrong Result",
            callback_data=f"recheck_menu"
        )
    ])

    return InlineKeyboardMarkup(buttons)


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
    # lang=None, quality=None
    files = await db.get_search_results(query, lang=None, quality=None)

    # Log Analytics
    asyncio.create_task(
        analytics.log_search(message.text, query, len(files), message.from_user.id, message.chat.id)
    )

    if not files:
        return 

    # Generate Buttons (Initial state: No filters)
    reply_markup = await btn_parser(search_id, files, client, offset=0, active_lang=None, active_qual=None)

    await message.reply_text(
        text=f"🔎 **Found {len(files)} results for:** `{query}`\n👇 **Select Filters or Click to Download:**",
        reply_markup=reply_markup,
        quote=True
    )


# ==========================================
# 2. COMBINED FILTER & PAGINATION HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^(next|filter)_"))
async def filter_pagination_handler(client: Client, callback: CallbackQuery):
    """
    Handles Next Page AND Filter Clicks in one robust function.
    Data Format: action_searchID_offset_lang_qual
    Example: next_102_10_hindi_720p
    """
    data = callback.data.split("_")
    
    try:
        # action = data[0] (not needed explicitly)
        search_id = int(data[1])
        offset = int(data[2])
        
        # Safe Extraction for Lang & Qual (Handle "None" strings)
        active_lang = data[3]
        if active_lang == "None": active_lang = None
        
        active_qual = data[4]
        if active_qual == "None": active_qual = None
        
    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    # 1. Retrieve Original Query
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired (48h). Please type query again.", show_alert=True)

    # 2. Database Search with Filters 
    # Even if offset is 0 (new filter clicked), we must query DB to get counts
    files = await db.get_search_results(
        query, 
        lang=active_lang, 
        quality=active_qual
    )
    
    # 3. Handle Empty Results (But keep buttons alive!)
    if not files:
        if offset > 0:
            return await callback.answer("⚠️ End of results.", show_alert=True)
        else:
            await callback.answer("⚠️ No files found for this filter combination!", show_alert=False)
            # We continue below to render the buttons (so user can uncheck)

    # 4. Generate Updated Buttons
    new_markup = await btn_parser(
        search_id, 
        files, 
        client, 
        offset, 
        active_lang=active_lang, 
        active_qual=active_qual
    )

    # 5. Build Status Text
    filter_status = ""
    if active_lang: filter_status += f"🏳️ {active_lang.title()} "
    if active_qual: filter_status += f"💿 {active_qual}"
    
    if filter_status:
        text_content = f"🔎 **Results for:** `{query}`\n⚙️ **Active Filters:** {filter_status}"
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
