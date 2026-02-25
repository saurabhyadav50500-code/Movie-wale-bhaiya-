import asyncio
import math
import re
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified

# Database & Utils Imports
from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
# ⚠️ Note: Naya size_menu_buttons yahan add kiya gaya hai
from utils import get_size, btn_parser, sort_menu_buttons, lang_menu_buttons, qual_menu_buttons, year_menu_buttons, size_menu_buttons

# ==========================================
# 🧹 HELPER: CLEAN DISPLAY NAME (UPDATED FIX)
# ==========================================
def clean_display_name(filename):
    """
    File name ko clean karta hai display ke liye.
    Removes: @usernames, brackets, extensions, promo tags.
    User Request: Remove (@ ; ' _ : *) and [Tg:-@Vpfills] type tags.
    """
    if not filename:
        return "Unknown File"

    # 1. Remove Extension (e.g., .mkv, .mp4)
    filename = re.sub(r'\.[a-z0-9]{2,5}$', '', filename, flags=re.IGNORECASE)

    # 2. ⚡ Remove Specific Promo Tags like [Tg:-@VPFILLS] or [Tg-@Name]
    # Ye line specifically us tag ko hatayegi jo screenshot me hai
    filename = re.sub(r'\[\s*(?:Tg|Telegram)[:\-_]*@?\w+.*?\]', '', filename, flags=re.IGNORECASE)
    
    # 3. Remove Usernames (@name) & Links
    filename = re.sub(r'@\w+', '', filename)
    filename = re.sub(r'(?:https?://|www\.)\S+', '', filename)

    # 4. Remove Specific Characters requested (@ ; ' _ : *) and Brackets
    # Regex me in sabko space se replace kar rahe hain
    filename = re.sub(r'[@;\'_:\*\[\]\(\)\{\}<>\|\.\-]', ' ', filename)

    # 5. Fix Extra Spaces (Agar cleanup ke baad zyada gap ho jaye)
    filename = re.sub(r'\s+', ' ', filename).strip()
    
    return filename

# ==========================================
# 1. TEXT HANDLERS (Group & PM)
# ==========================================

# Handler for GROUPS
@Client.on_message(filters.text & filters.group & ~filters.regex(r"^/"))
async def auto_filter_group(client: Client, message: Message):
    await process_search(client, message, is_pm=False)

# Handler for PM/PRIVATE
@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"))
async def auto_filter_pm(client: Client, message: Message):
    await process_search(client, message, is_pm=True)

# Common Search Function - (Updated for Sort support)
async def process_search(client, message, is_pm):
    query = message.text
    if not query or len(query) < 2 or query.startswith("/"): return
    if not client.me: await client.get_me()

    if not is_pm:
        await db_users.get_group_status(message.chat.id)
    
    # Save Query for Analytics & ID
    search_id = await db.save_search_query(query, message.from_user.id)
    asyncio.create_task(analytics.log_search(message.text, query, 0, message.from_user.id, message.chat.id))

    if not search_id: 
        if is_pm: await message.reply("❌ Database Error.")
        return

    # 🔎 Search in DB (Initial Search, No Sort)
    files = await db.get_search_results(query)
    years = await db.get_unique_years(query)

    # Result Handling
    if not files:
        if is_pm:
            await message.reply_text(f"❌ **No Results Found for:** `{query}`\n\nKripya spelling check karein.")
        return

    # Generate Buttons (Pass a_sort=None explicitly)
    reply_markup = await btn_parser(
        search_id, 
        files, 
        client, 
        offset=0, 
        years=years, 
        a_sort=None
    )

    await message.reply_text(
        text=f"🔎 **Results for:** `{query}`\n👇 **Select Filters:**",
        reply_markup=reply_markup,
        quote=True if not is_pm else False
    )

# ==========================================
# 2. CALLBACK HANDLER (Filters & Pagination, Sort, Lang, Qual, Year, Size)
# ==========================================
# Regex update kiya hai 'sizemenu' ko support karne ke liye
@Client.on_callback_query(filters.regex(r"^(next|filter|sortmenu|langmenu|qualmenu|yearmenu|sizemenu)_"))
async def filter_pagination_handler(client: Client, callback: CallbackQuery):
    data = callback.data.split("_")
    action = data[0] # 'filter', 'next', 'sortmenu', 'langmenu', 'qualmenu', 'yearmenu' or 'sizemenu'
    
    try:
        # Data format: action_id_offset_type_lang_qual_year_size_sort
        search_id = int(data[1])
        offset = int(data[2])
        
        def c(v): return None if v == "None" else v
        
        # Safely parse parameters (Existing + New Sort Param)
        a_type = c(data[3]) if len(data) > 3 else None
        a_lang = c(data[4]) if len(data) > 4 else None
        a_qual = c(data[5]) if len(data) > 5 else None
        a_year = c(data[6]) if len(data) > 6 else None
        a_size = c(data[7]) if len(data) > 7 else None
        # 🆕 New Sort Parameter (Index 8)
        a_sort = c(data[8]) if len(data) > 8 else None 

    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    # --- 💾 HANDLE SIZE MENU CLICK ---
    if action == "sizemenu":
        new_markup = await size_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort)
        try:
            await callback.edit_message_reply_markup(reply_markup=new_markup)
        except errors.MessageNotModified: pass
        return

    # --- 📅 HANDLE YEAR MENU CLICK ---
    if action == "yearmenu":
        query = await db.get_search_query(search_id)
        if not query:
            return await callback.answer("❌ Search Expired.", show_alert=True)
            
        years = await db.get_unique_years(query)
        new_markup = await year_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort, years)
        try:
            await callback.edit_message_reply_markup(reply_markup=new_markup)
        except errors.MessageNotModified: pass
        return

    # --- 📺 HANDLE QUALITY MENU CLICK ---
    if action == "qualmenu":
        new_markup = await qual_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort)
        try:
            await callback.edit_message_reply_markup(reply_markup=new_markup)
        except errors.MessageNotModified: pass
        return

    # --- 🗣️ HANDLE LANGUAGE MENU CLICK ---
    if action == "langmenu":
        new_markup = await lang_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort)
        try:
            await callback.edit_message_reply_markup(reply_markup=new_markup)
        except errors.MessageNotModified: pass
        return

    # --- 🆕 HANDLE SORT MENU CLICK ---
    if action == "sortmenu":
        # Ye sub-menu open karega
        new_markup = await sort_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort)
        try:
            await callback.edit_message_reply_markup(reply_markup=new_markup)
        except errors.MessageNotModified: pass
        return

    # --- NORMAL FILTER & SEARCH LOGIC ---
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired.", show_alert=True)

    # Search with Filters (Pass a_sort to DB)
    files = await db.get_search_results(
        query, 
        file_type=a_type, 
        lang=a_lang, 
        quality=a_qual, 
        year=a_year, 
        size_key=a_size,
        sort_key=a_sort, # 🆕 Sorting apply karein
        offset=offset
    )
    years = await db.get_unique_years(query)

    if not files:
        if offset > 0:
            return await callback.answer("⚠️ End of pages.", show_alert=True)
        else:
            await callback.answer("⚠️ No files found for this combo!", show_alert=False)

    # Update Buttons (Pass a_sort logic so it persists)
    new_markup = await btn_parser(
        search_id, files, client, offset, 
        a_type, a_lang, a_qual, a_year, a_size, a_sort, 
        years=years
    )
    
    text = f"🔎 **Results for:** `{query}`"
    status = []
    if a_type: status.append(f"{a_type.title()}")
    if a_lang: status.append(f"{a_lang.title()}")
    if a_qual: status.append(f"{a_qual}")
    if a_year: status.append(f"{a_year}")
    
    # 🆕 Show Active Size in Text
    if a_size:
        size_names = {"s": "<500MB", "m": "500MB - 1GB", "l": "1GB - 2GB", "xl": ">2GB"}
        status.append(size_names.get(a_size, a_size))
        
    # 🆕 Show Active Sort in Text
    if a_sort:
        sort_names = {"new": "Newest", "old": "Oldest", "max": "Largest", "min": "Smallest"}
        sort_label = sort_names.get(a_sort, a_sort)
        status.append(f"📂 {sort_label}")
    
    if status: text += f"\n⚙️ **Active:** {', '.join(status)}"

    try:
        await callback.edit_message_text(text=text, reply_markup=new_markup)
    except MessageNotModified:
        pass

# ==========================================
# 3. FILE DELIVERY
# ==========================================
@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client, message):
    if len(message.command) < 2 or not message.command[1].startswith("file_"): return
    
    link_id = message.command[1].split("file_", 1)[1]
    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info: 
        return await message.reply("❌ File not found (Deleted or Invalid).")
    
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    
    # Cleaning Name for display (Uses UPDATED clean_display_name)
    raw_name = file_info.get('file_name', 'Unknown File')
    clean_name = clean_display_name(raw_name)

    s_msg = await message.reply(f"📂 **Sending:** `{clean_name}`")
    
    try:
        await client.send_cached_media(
            message.from_user.id, 
            file_info['file_id'], 
            caption=file_info['caption'] or ""
        )
        await s_msg.delete()
    except Exception as e:
        await s_msg.edit(f"❌ Error: {e}")

# ==========================================
# 4. MISC HANDLERS
# ==========================================
@Client.on_callback_query(filters.regex("pages"))
async def pages_handler(_, cb): 
    await cb.answer("ℹ️ Current Page", show_alert=True)

@Client.on_callback_query(filters.regex("recheck_menu"))
async def close_handler(_, cb): 
    await cb.message.delete()
