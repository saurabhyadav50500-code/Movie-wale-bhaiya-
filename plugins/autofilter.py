import math
import time
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified, FloodWait, UserIsBlocked, InputUserDeactivated

# Database & Utils Imports
from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10
SPAM_CACHE = {}  # Stores user_id: timestamp

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================

def is_spam(user_id):
    """
    Prevents spamming. Returns True if clicked/messaged within 1.5 seconds.
    """
    now = time.time()
    last_time = SPAM_CACHE.get(user_id, 0)
    SPAM_CACHE[user_id] = now
    return (now - last_time) < 1.5

def filter_files_by_type(files, active_type):
    if active_type == "all":
        return files
    
    filtered = []
    for file in files:
        mime = str(file.get("mime_type", "")).lower()
        f_type = str(file.get("file_type", "")).lower()
        is_video = "video" in mime or f_type == "video"
        
        if active_type == "video" and is_video:
            filtered.append(file)
        elif active_type == "document" and not is_video:
            filtered.append(file)
            
    return filtered

async def arrange_buttons(search_id, all_files, offset, active_type, bot_username):
    filtered_files = filter_files_by_type(all_files, active_type)
    total_files = len(filtered_files)
    
    if total_files == 0:
        return None, 0

    end_index = offset + BUTTONS_PER_PAGE
    current_files = filtered_files[offset:end_index]

    buttons = []

    # FILES
    for file in current_files:
        f_id = file.get('link_id')
        f_name = file.get('file_name', 'Unknown')
        f_size = get_size(file.get('file_size', 0))
        if len(f_name) > 30: f_name = f_name[:27] + "..."
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )
        ])

    # FILTERS
    vid_icon = "✅ Videos" if active_type == "video" else "🎞️ Videos"
    doc_icon = "✅ Docs" if active_type == "document" else "📂 Docs"
    all_icon = "✅ All" if active_type == "all" else "All Media"

    buttons.append([
        InlineKeyboardButton(vid_icon, callback_data=f"spage_{search_id}_video_0"),
        InlineKeyboardButton(doc_icon, callback_data=f"spage_{search_id}_document_0"),
        InlineKeyboardButton(all_icon, callback_data=f"spage_{search_id}_all_0")
    ])

    # PAGINATION
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []
    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"spage_{search_id}_{active_type}_{offset - BUTTONS_PER_PAGE}"))
    else:
        nav_buttons.append(InlineKeyboardButton("░", callback_data="ignore"))

    nav_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="pages"))

    if end_index < total_files:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{search_id}_{active_type}_{end_index}"))
    else:
        nav_buttons.append(InlineKeyboardButton("░", callback_data="ignore"))

    buttons.append(nav_buttons)
    return InlineKeyboardMarkup(buttons), total_files

# ==========================================
# 1. MAIN SEARCH HANDLER (With FloodWait Fix)
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    if not query or len(query) < 2 or query.startswith("/"): return

    # 🛑 1. TEXT SPAM PROTECTION
    # Agar user jaldi-jaldi message kar raha hai to ignore karein
    if is_spam(message.from_user.id):
        return 

    tasks = [
        db_users.get_group_status(message.chat.id),
        db.get_search_results(query),
        db.save_search_query(query, message.from_user.id)
    ]
    
    # Background Analytics
    asyncio.create_task(analytics.log_search(message.text, query, 0, message.from_user.id, message.chat.id))

    results = await asyncio.gather(*tasks)
    files, search_id = results[1], results[2]

    if not files or not search_id: return
    if not client.me: await client.get_me()

    reply_markup, total = await arrange_buttons(search_id, files, 0, "all", client.me.username)
    if not reply_markup: return

    # 🛡️ 2. FLOODWAIT HANDLING
    try:
        await message.reply_text(
            text=f"🔎 **Found {total} results for:** `{query}`",
            reply_markup=reply_markup,
            quote=True
        )
    except FloodWait as e:
        print(f"⚠️ FloodWait in AutoFilter: Sleeping {e.value}s")
        await asyncio.sleep(e.value)
        # Retry once after sleeping
        try:
            await message.reply_text(
                text=f"🔎 **Found {total} results for:** `{query}`",
                reply_markup=reply_markup,
                quote=True
            )
        except Exception:
            pass # Ignore if fails again
    except Exception as e:
        print(f"Auto Filter Error: {e}")

# ==========================================
# 2. CALLBACK HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^spage_"))
async def spage_handler(client: Client, callback: CallbackQuery):
    await callback.answer()
    if is_spam(callback.from_user.id): return

    try:
        _, str_id, active_type, str_offset = callback.data.split("_", 3)
        search_id, offset = int(str_id), int(str_offset)
    except: return

    query = await db.get_search_query(search_id)
    if not query: return await callback.message.edit("⚠️ **Search Expired**")

    files = await db.get_search_results(query)
    if not files: return await callback.message.edit("❌ No files found.")

    if not client.me: await client.get_me()

    reply_markup, total = await arrange_buttons(search_id, files, offset, active_type, client.me.username)
    if not reply_markup: return await callback.answer("❌ No files found.", show_alert=True)

    try:
        await callback.message.edit_text(
            f"🔎 **Found {total} results for:** `{query}`\nFilter: **{active_type.title()}**",
            reply_markup=reply_markup
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await callback.message.edit_text(
                f"🔎 **Found {total} results for:** `{query}`\nFilter: **{active_type.title()}**",
                reply_markup=reply_markup
            )
        except: pass
    except MessageNotModified: pass

# ==========================================
# 3. UTILITY HANDLERS
# ==========================================
@Client.on_callback_query(filters.regex(r"^(ignore|pages)"))
async def utility_callback(client, callback):
    msg = "This is the page counter." if "pages" in callback.data else ""
    await callback.answer(msg, show_alert="pages" in callback.data)

@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client, callback): await callback.message.delete()

# ==========================================
# 4. FILE DELIVERY (HIGH PRIORITY)
# ==========================================
@Client.on_message(filters.command("start") & filters.private, group=-10)
async def file_delivery_handler(client: Client, message: Message):
    if len(message.command) < 2: return
    payload = message.command[1]
    if not payload.startswith("file_"): return

    try:
        link_id = payload.split("file_", 1)[1]
    except IndexError: return

    file_info = await db.get_file_by_link_id(link_id)
    if not file_info: return await message.reply("❌ File not found (Deleted).")

    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    status_msg = await message.reply("📂 **Sending File...**")

    try:
        chat_id = file_info.get('chat_id')
        msg_id = file_info.get('message_id')
        caption = file_info.get('caption', "")[:1024]

        # Method 1: Copy
        if chat_id and msg_id:
            try:
                await client.copy_message(message.from_user.id, chat_id, msg_id, caption=caption)
                await status_msg.delete()
                return
            except Exception: pass
        
        # Method 2: Send Cached
        await client.send_cached_media(message.from_user.id, file_info['file_id'], caption=caption)
        await status_msg.delete()

    except Exception as e:
        err = str(e)
        if "MEDIA_EMPTY" in err or "400" in err or "ID_INVALID" in err:
             await db.col.delete_one({"link_id": link_id})
             await status_msg.edit("❌ **File Expired:** Original file was deleted.")
        elif "FloodWait" in err:
             await status_msg.edit("⏳ **Server Busy:** Please try again in 10 seconds.")
        else:
             await status_msg.edit(f"❌ Error: {err}")
