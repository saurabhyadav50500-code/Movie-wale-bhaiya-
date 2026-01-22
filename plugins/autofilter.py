import math
import time
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified, FloodWait

# Database & Utils Imports
from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10
SPAM_CACHE = {}  # Stores user_id: timestamp

# ==========================================
# 🛠️ HELPER FUNCTIONS (Logic & Layout)
# ==========================================

def is_spam(user_id):
    """
    Prevents button spamming. Returns True if clicked within 1 second.
    """
    now = time.time()
    last_time = SPAM_CACHE.get(user_id, 0)
    SPAM_CACHE[user_id] = now
    return (now - last_time) < 1.0

def filter_files_by_type(files, active_type):
    """
    Filters the raw file list based on the active tab (Video/Document).
    """
    if active_type == "all":
        return files
    
    filtered = []
    for file in files:
        # Determine type based on mime_type or file_type attribute
        mime = str(file.get("mime_type", "")).lower()
        f_type = str(file.get("file_type", "")).lower()
        
        # Check if it's a video
        is_video = "video" in mime or f_type == "video"
        
        if active_type == "video" and is_video:
            filtered.append(file)
        elif active_type == "document" and not is_video:
            filtered.append(file)
            
    return filtered

async def arrange_buttons(search_id, all_files, offset, active_type, bot_username):
    """
    Constructs the specific button layout:
    1. File Results
    2. Filters [Vid] [Doc] [All]
    3. Pagination
    """
    # 1. Filter & Slice Files
    filtered_files = filter_files_by_type(all_files, active_type)
    total_files = len(filtered_files)
    
    # Handle Empty Result after Filtering
    if total_files == 0:
        return None, 0

    end_index = offset + BUTTONS_PER_PAGE
    current_files = filtered_files[offset:end_index]

    buttons = []

    # --- ROW 1: FILE RESULTS ---
    for file in current_files:
        f_id = file.get('link_id')
        f_name = file.get('file_name', 'Unknown')
        f_size = get_size(file.get('file_size', 0))
        
        # Truncate Long Names to fit button
        if len(f_name) > 30:
            f_name = f_name[:27] + "..."
            
        buttons.append([
            InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )
        ])

    # --- ROW 2: TYPE FILTERS ---
    # Highlights the currently selected button with ✅
    vid_icon = "✅ Videos" if active_type == "video" else "🎞️ Videos"
    doc_icon = "✅ Docs" if active_type == "document" else "📂 Docs"
    all_icon = "✅ All" if active_type == "all" else "All Media"

    # Clicking a filter resets offset to 0
    filter_buttons = [
        InlineKeyboardButton(vid_icon, callback_data=f"spage_{search_id}_video_0"),
        InlineKeyboardButton(doc_icon, callback_data=f"spage_{search_id}_document_0"),
        InlineKeyboardButton(all_icon, callback_data=f"spage_{search_id}_all_0")
    ]
    buttons.append(filter_buttons)

    # --- ROW 3: PAGINATION ---
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []

    # Back Button
    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data=f"spage_{search_id}_{active_type}_{offset - BUTTONS_PER_PAGE}"
            )
        )
    else:
        # Placeholder to keep alignment
        nav_buttons.append(InlineKeyboardButton("░", callback_data="ignore"))

    # Page Counter (Non-clickable)
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"{current_page}/{total_pages}",
            callback_data="pages"
        )
    )

    # Next Button
    if end_index < total_files:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"spage_{search_id}_{active_type}_{end_index}"
            )
        )
    else:
        nav_buttons.append(InlineKeyboardButton("░", callback_data="ignore"))

    buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons), total_files

# ==========================================
# 1. MAIN SEARCH HANDLER (Optimized & Parallel)
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    
    if not query or len(query) < 2 or query.startswith("/"):
        return

    # 🚀 PARALLEL EXECUTION (Asyncio Gather)
    # We fetch Group Settings, Search Results, and Save Query at the exact same time.
    
    tasks = [
        db_users.get_group_status(message.chat.id),        # 0: Settings (Cache)
        db.get_search_results(query),                      # 1: Search Files
        db.save_search_query(query, message.from_user.id)  # 2: Save Query (Get ID)
    ]
    
    # Run Analytics in background (Fire & Forget)
    asyncio.create_task(analytics.log_search(
        raw_query=message.text, cleaned_query=query, results_count=0,
        user_id=message.from_user.id, chat_id=message.chat.id
    ))

    # Wait for critical data to arrive
    results = await asyncio.gather(*tasks)
    
    settings = results[0]
    files = results[1]
    search_id = results[2]

    # Optional: Check if bot is disabled in group (Using Cached Settings)
    # if not settings.get('is_enabled', True): return

    if not files:
        return # No results found, stay silent

    if not search_id:
        return await message.reply("❌ Database Error. Please try again.")

    if not client.me:
        await client.get_me()

    # Generate Layout (Default: active_type='all', offset=0)
    reply_markup, total = await arrange_buttons(search_id, files, 0, "all", client.me.username)

    if not reply_markup:
        return

    await message.reply_text(
        text=f"🔎 **Found {total} results for:** `{query}`\nSelect a category below:",
        reply_markup=reply_markup,
        quote=True
    )

# ==========================================
# 2. UNIFIED CALLBACK HANDLER (Pagination + Filters)
# ==========================================
@Client.on_callback_query(filters.regex(r"^spage_"))
async def spage_handler(client: Client, callback: CallbackQuery):
    # 🚀 1. UX: Stop Loading Spinner Immediately
    await callback.answer()

    # 🚀 2. Anti-Spam Check
    if is_spam(callback.from_user.id):
        return # Ignore click if too fast

    data = callback.data
    try:
        # Format: spage_{search_id}_{active_type}_{offset}
        # Example: spage_55_video_10
        _, str_id, active_type, str_offset = data.split("_", 3)
        search_id = int(str_id)
        offset = int(str_offset)
    except Exception:
        return 

    # 3. Fetch Query from DB (Using ID)
    query = await db.get_search_query(search_id)
    
    if not query:
        return await callback.message.edit(
            "⚠️ **Search Expired**\nPlease request the movie again."
        )

    # 4. Fetch Files (Fresh from DB)
    files = await db.get_search_results(query)
    
    if not files:
        return await callback.message.edit("❌ No files found.")

    if not client.me:
        await client.get_me()

    # 5. Generate New Layout (Preserving Active Type)
    reply_markup, total_files = await arrange_buttons(search_id, files, offset, active_type, client.me.username)

    if not reply_markup:
        return await callback.answer("❌ No files found in this category.", show_alert=True)

    # 6. Safe Edit
    try:
        await callback.message.edit_text(
            text=f"🔎 **Found {total_files} results for:** `{query}`\nFilter: **{active_type.title()}**",
            reply_markup=reply_markup
        )
    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        print(f"Pagination Error: {e}")

# ==========================================
# 3. UTILITY HANDLERS
# ==========================================

@Client.on_callback_query(filters.regex(r"^ignore"))
async def ignore_callback(client, callback):
    await callback.answer()

@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client, callback):
    await callback.message.delete()

@Client.on_callback_query(filters.regex(r"^pages"))
async def pages_handler(client, callback):
    await callback.answer("This is the page counter.", show_alert=True)

# ==========================================
# 4. FILE DELIVERY (DEEP LINK - HIGH PRIORITY) 🚀
# ==========================================
# Group -10 ensures this runs before other handlers to catch /start
@Client.on_message(filters.command("start") & filters.private, group=-10)
async def file_delivery_handler(client: Client, message: Message):
    if len(message.command) < 2:
        return
    
    payload = message.command[1]
    
    if not payload.startswith("file_"):
        return

    try:
        link_id = payload.split("file_", 1)[1]
    except IndexError:
        return 

    # 1. Fetch File Info
    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info:
        return await message.reply("❌ File not found (Deleted or Invalid).")

    # 2. Add User to DB (Cache)
    await db_users.add_user(message.from_user.id, message.from_user.first_name)

    status_msg = await message.reply("📂 **Sending File...**")

    # 3. SEND FILE (Robust Method)
    try:
        # Strategy A: Copy Message (Best - Preserves file attributes)
        chat_id = file_info.get('chat_id')
        msg_id = file_info.get('message_id')
        
        sent = False
        
        if chat_id and msg_id:
            try:
                await client.copy_message(
                    chat_id=message.from_user.id,
                    from_chat_id=chat_id,
                    message_id=msg_id,
                    caption=file_info.get('caption', "")[:1024]
                )
                sent = True
            except Exception as e:
                print(f"Copy Failed (Trying fallback): {e}")

        # Strategy B: Send Cached Media (Fallback if Copy fails or Original deleted)
        if not sent:
            await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_info['file_id'],
                caption=file_info.get('caption', "")[:1024]
            )
            
        await status_msg.delete()

    except Exception as e:
        err = str(e)
        print(f"Send Error: {err}")
        
        # If file is deleted from Telegram, remove from DB to clean up
        if "MEDIA_EMPTY" in err or "400" in err or "ID_INVALID" in err:
             await db.col.delete_one({"link_id": link_id})
             await status_msg.edit("❌ **File Expired:** Original file was deleted from Telegram.")
        else:
             await status_msg.edit(f"❌ Error sending file: {err}")
