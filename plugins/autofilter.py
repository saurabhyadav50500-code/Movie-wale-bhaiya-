import math
import asyncio
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

async def btn_parser(search_id, files, client, offset=0, active_filter=None):
    """
    Generates buttons with File Type Filters.
    active_filter: 'video', 'document', or None
    """
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []
    
    # Username safe fetch
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot" # Fallback

    # --- 1. FILE BUTTONS ---
    for file in current_files:
        f_id = file.get('link_id') 
        f_name = file.get('file_name', 'Unknown File')
        f_size = get_size(file.get('file_size', 0))
        
        if len(f_name) > 30:
            f_name = f_name[:27] + "..."
            
        # URL Button for PM Redirect
        buttons.append(
            [InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )]
        )

    # --- 2. FILTER BUTTONS ROW ---
    # Logic: Data format is filter_{search_id}_{type}
    
    filter_row = []
    
    # Video Button
    vid_text = "📹 Videos ✅" if active_filter == "video" else "📹 Videos"
    filter_row.append(InlineKeyboardButton(vid_text, callback_data=f"filter_{search_id}_video"))

    # Docs Button
    doc_text = "📂 Docs ✅" if active_filter == "document" else "📂 Docs"
    filter_row.append(InlineKeyboardButton(doc_text, callback_data=f"filter_{search_id}_document"))

    # All/Reset Button (Only show if a filter is active to save space, or always show)
    if active_filter is not None:
        filter_row.append(InlineKeyboardButton("🔄 All Files", callback_data=f"filter_{search_id}_all"))

    buttons.append(filter_row)

    # --- 3. PAGINATION BUTTONS ---
    # Logic: Data format is next_{search_id}_{offset}_{active_filter}
    
    total_files = len(files)
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []

    # Helper: Convert None to string 'none' for callback data
    filter_str = active_filter if active_filter else "none"

    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data=f"next_{search_id}_{offset - BUTTONS_PER_PAGE}_{filter_str}"
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
                callback_data=f"next_{search_id}_{end_index}_{filter_str}"
            )
        )

    buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(
            text="♻️ Close / Wrong Result",
            callback_data=f"recheck_menu"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# ==========================================
# 1. MAIN SEARCH HANDLER (Optimized)
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    
    if not query or len(query) < 2 or query.startswith("/"):
        return

    if not client.me:
        await client.get_me()

    # 🚀 STEP 1: CHECK GROUP SETTINGS
    settings = await db_users.get_group_status(message.chat.id)

    # 🚀 STEP 2: PARALLEL EXECUTION
    # Default search: No filter (file_type=None)
    search_task = asyncio.create_task(db.get_search_results(query, file_type=None))
    save_task = asyncio.create_task(db.save_search_query(query, message.from_user.id))

    # Log Analytics
    asyncio.create_task(
        analytics.log_search(message.text, query, 0, message.from_user.id, message.chat.id)
    )

    files, search_id = await asyncio.gather(search_task, save_task)

    if not files:
        return 

    if not search_id:
        return await message.reply("❌ Database Error. Please try again.")

    # Generate Buttons (active_filter defaults to None)
    reply_markup = await btn_parser(search_id, files, client, offset=0, active_filter=None)

    await message.reply_text(
        text=f"🔎 **Found {len(files)} results for:** `{query}`\n\n👇 **Click below to get file in PM:**",
        reply_markup=reply_markup,
        quote=True
    )


# ==========================================
# 2. FILTER HANDLER (NEW: Handles Video/Docs Clicks)
# ==========================================
@Client.on_callback_query(filters.regex(r"^filter_"))
async def filter_handler(client: Client, callback: CallbackQuery):
    data = callback.data
    # Format: filter_{search_id}_{type}
    try:
        _, str_id, filter_type = data.split("_")
        search_id = int(str_id)
    except (ValueError, IndexError):
        return await callback.answer("❌ Error parsing data.")

    # Determine Database Filter
    if filter_type == "all":
        db_filter = None
    else:
        db_filter = filter_type # 'video' or 'document'

    # Get Original Query
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired.", show_alert=True)

    # Search with New Filter 
    files = await db.get_search_results(query, file_type=db_filter)
    
    if not files:
        return await callback.answer(f"❌ No {filter_type}s found!", show_alert=True)

    # Generate New Buttons (Reset offset to 0)
    new_markup = await btn_parser(search_id, files, client, offset=0, active_filter=db_filter)

    try:
        await callback.edit_message_text(
            text=f"🔎 **Found {len(files)} results for:** `{query}`\n🔽 **Filter:** {filter_type.title()}",
            reply_markup=new_markup
        )
    except MessageNotModified:
        pass


# ==========================================
# 3. PAGINATION HANDLER (Updated for Filters)
# ==========================================
@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page_handler(client: Client, callback: CallbackQuery):
    data = callback.data
    
    try:
        # Data format: next_{search_id}_{offset}_{filter_type}
        parts = data.split("_")
        str_id = parts[1]
        offset = int(parts[2])
        
        # Check for filter part (Backward compatibility)
        if len(parts) > 3:
            filter_str = parts[3]
            active_filter = None if filter_str == "none" else filter_str
        else:
            active_filter = None

    except (ValueError, IndexError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    if not str_id.isdigit():
         return await callback.answer("❌ Invalid Search ID.", show_alert=True)
         
    search_id = int(str_id)

    # 1. Fetch Query
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired.", show_alert=True)

    # 2. Search (Pass the active filter)
    files = await db.get_search_results(query, file_type=active_filter)
    
    if not files:
        return await callback.answer("❌ No files found.", show_alert=True)

    if not client.me:
        await client.get_me()

    # 3. Generate New Buttons (Pass the active filter)
    new_markup = await btn_parser(search_id, files, client, offset=offset, active_filter=active_filter)

    try:
        await callback.edit_message_reply_markup(reply_markup=new_markup)
    except MessageNotModified:
        pass 
    except Exception as e:
        print(f"Pagination Error: {e}")


# ==========================================
# 4. FILE DELIVERY & CLOSE HANDLERS (Unchanged)
# ==========================================
@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client: Client, message: Message):
    if len(message.command) < 2: return
    payload = message.command[1]
    if not payload.startswith("file_"): return

    try:
        link_id = payload.split("file_", 1)[1]
    except IndexError:
        return await message.reply("❌ Invalid Link Format")

    file_info = await db.get_file_by_link_id(link_id)
    if not file_info: return await message.reply("❌ File not found.")

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
        if "MEDIA_EMPTY" in str(e) or "400" in str(e):
             await db.col.delete_one({"link_id": link_id})
             await status_msg.edit("❌ **File Expired:** Deleted from Telegram.")
        else:
             await status_msg.edit(f"❌ Error: {str(e)}")

@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client: Client, callback: CallbackQuery):
    await callback.message.delete()
