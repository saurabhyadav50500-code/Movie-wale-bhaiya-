import math
import asyncio
import re  # 👈 Cleaning ke liye
import random
import string
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified
from database.ia_filterdb import db
from database.analytics import analytics
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

# --- MEMORY STORAGE ---
BUTTON_STORAGE = {} 

# ==========================================
# 🧹 SMART FILE NAME CLEANER
# ==========================================
def clean_display_name(filename):
    """
    File name ko clean karta hai display ke liye.
    Removes: @usernames, brackets, extensions, dots, underscores.
    Keeps: Year, Resolution, Movie Name.
    """
    if not filename:
        return "Unknown File"

    # 1. Remove File Extension (.mkv, .mp4, etc.)
    filename = re.sub(r'\.[a-z0-9]{2,5}$', '', filename, flags=re.IGNORECASE)

    # 2. Remove Usernames (@tag, Tg:@tag)
    filename = re.sub(r'@\w+', '', filename)
    filename = re.sub(r'(?:Tg|Telegram):?@?\w+', '', filename, flags=re.IGNORECASE)

    # 3. Remove Links (http, www, .com)
    filename = re.sub(r'(?:https?://|www\.)\S+', '', filename)

    # 4. Replace Brackets, Pipes, Underscores, Dots with SPACE
    # Hum content delete nahi kar rahe, bas symbols hata kar space de rahe hain
    # Taaki "Movie.2024" ban jaye "Movie 2024"
    filename = re.sub(r'[\[\]\(\)\|\_\.\-]', ' ', filename)

    # 5. Fix Extra Spaces (Collapse multiple spaces to one)
    filename = re.sub(r'\s+', ' ', filename).strip()

    return filename


# --- UTILS ---
def get_search_id():
    """Generates a short random ID (8 chars)"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

async def btn_parser(search_id: str, files: list, client: Client, offset: int = 0):
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
        raw_name = file.get('file_name', 'Unknown File')
        f_size = get_size(file.get('file_size', 0))
        
        # 👇 CLEANING FUNCTION APPLIED HERE
        # Button me dikhane ke liye naam saaf kiya ja raha hai
        f_name = clean_display_name(raw_name)
        
        # Button text limit (Telegram limit ~64 chars)
        if len(f_name) > 35:
            f_name = f_name[:32] + "..."
            
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
                callback_data=f"next_{search_id}_{offset - BUTTONS_PER_PAGE}"
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
                callback_data=f"next_{search_id}_{end_index}"
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

    if not client.me:
        await client.get_me()

    # Database Search
    files = await db.get_search_results(query)

    # --- 📊 ANALYTICS LOGGING ---
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

    if not files:
        return 

    # Generate Short ID for this search
    search_id = get_search_id()
    BUTTON_STORAGE[search_id] = query  # Map ID -> Real Query

    # btn_parser ko ab ID pass karenge
    reply_markup = await btn_parser(search_id, files, client, offset=0)

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
        # Data format: next_{search_id}_{offset}
        _, search_id, str_offset = data.split("_", 2)
        offset = int(str_offset)
    except (ValueError, IndexError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    # Retrieve Real Query using ID
    query = BUTTON_STORAGE.get(search_id)
    
    if not query:
        return await callback.answer("❌ Search expired. Please search again.", show_alert=True)

    files = await db.get_search_results(query)
    if not files:
        return await callback.answer("❌ No files found.", show_alert=True)

    if not client.me:
        await client.get_me()

    new_markup = await btn_parser(search_id, files, client, offset=offset)

    try:
        await callback.edit_message_reply_markup(reply_markup=new_markup)
    except MessageNotModified:
        pass 
    except Exception as e:
        print(f"Pagination Error: {e}")


# ==========================================
# 3. FILE DELIVERY HANDLER (Priority High)
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

    # 👇 Clean Name for Display Message
    raw_name = file_info.get('file_name', 'Unknown File')
    clean_name = clean_display_name(raw_name)

    status_msg = await message.reply(f"📂 **Sending:** `{clean_name}`")

    try:
        await client.send_cached_media(
            chat_id=message.from_user.id,
            file_id=file_info['file_id'],
            caption=file_info['caption'] or "",
        )
        await status_msg.delete()
    
    except Exception as e:
        print(f"Error Sending File: {e}")
        # Auto Delete Logic for Invalid Files
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
