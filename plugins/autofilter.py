import math
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified
from database.ia_filterdb import db
from database.analytics import analytics  # 👈 Analytics Import
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

async def btn_parser(query: str, files: list, client: Client, offset: int = 0):
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []
    
    # Username safe fetch
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot" # Fallback

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

    total_files = len(files)
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []

    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data=f"next_{query}_{offset - BUTTONS_PER_PAGE}"
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
                callback_data=f"next_{query}_{end_index}"
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
# 1. MAIN SEARCH HANDLER (Group Text)
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    
    if not query or len(query) < 2 or query.startswith("/"):
        return

    # Bot Identity Ensure karein
    if not client.me:
        await client.get_me()

    # Database Search
    files = await db.get_search_results(query)

    # --- 📊 ANALYTICS LOGGING (New) ---
    # Search data background me save hoga
    if query:
        asyncio.create_task(
            analytics.log_search(
                raw_query=message.text, 
                cleaned_query=query, 
                results_count=len(files), 
                user_id=message.from_user.id, 
                chat_id=message.chat.id
            )
        )
    # ----------------------------------

    if not files:
        return 

    reply_markup = await btn_parser(query, files, client, offset=0)

    await message.reply_text(
        text=f"🔎 **Found {len(files)} results for:** `{query}`\n\n👇 **Click below to get file in PM:**",
        reply_markup=reply_markup,
        quote=True
    )


# ==========================================
# 2. PAGINATION HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page_handler(client: Client, callback: CallbackQuery):
    data = callback.data
    
    try:
        prefix_query, str_offset = data.rsplit("_", 1)
        query = prefix_query.split("_", 1)[1]
        offset = int(str_offset)
    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing pagination data.", show_alert=True)

    files = await db.get_search_results(query)
    if not files:
        return await callback.answer("❌ Search results expired.", show_alert=True)

    if not client.me:
        await client.get_me()

    new_markup = await btn_parser(query, files, client, offset=offset)

    try:
        await callback.edit_message_reply_markup(reply_markup=new_markup)
    except MessageNotModified:
        pass 
    except Exception as e:
        print(f"Pagination Error: {e}")


# ==========================================
# 3. FILE DELIVERY HANDLER (Priority High)
# ==========================================
# group=-1 ka matlab ye handler sabse pehle check hoga.
@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client: Client, message: Message):
    """
    Handles deep link delivery. High priority.
    """
    if len(message.command) < 2:
        return
    
    payload = message.command[1] # "file_xyz123"
    
    if not payload.startswith("file_"):
        return

    try:
        link_id = payload.split("file_", 1)[1]
    except IndexError:
        return await message.reply("❌ Invalid Link Format")

    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info:
        return await message.reply("❌ File not found (Deleted or Invalid).")

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
        # Auto Delete Logic for Invalid Files (Optional but Recommended)
        if "MEDIA_EMPTY" in str(e) or "400" in str(e):
             await db.col.delete_one({"link_id": link_id})
             await status_msg.edit("❌ **File Expired:** This file was deleted from Telegram servers.")
        else:
             await status_msg.edit(f"❌ Error sending file: {str(e)}")


# ==========================================
# 4. CLOSE HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client: Client, callback: CallbackQuery):
    await callback.message.delete()
