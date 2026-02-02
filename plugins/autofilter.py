import asyncio
import math
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified

# Database & Utils Imports
from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
from utils import get_size 
# Note: btn_parser humne yahi define kiya hai taaki layout fix rahe

# ==========================================
# 🧹 HELPER: CLEAN DISPLAY NAME
# ==========================================
def clean_display_name(filename):
    """
    File name ko clean karta hai display ke liye.
    Removes: @usernames, brackets, extensions, dots, underscores.
    """
    if not filename:
        return "Unknown File"

    # 1. Remove Extension
    filename = re.sub(r'\.[a-z0-9]{2,5}$', '', filename, flags=re.IGNORECASE)
    # 2. Remove Usernames & Promos
    filename = re.sub(r'@\w+', '', filename)
    filename = re.sub(r'(?:Tg|Telegram):?@?\w+', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'(?:https?://|www\.)\S+', '', filename)
    # 3. Replace Brackets, Pipes, Underscores with Space
    filename = re.sub(r'[\[\]\(\)\|\_\.\-]', ' ', filename)
    # 4. Fix Spaces
    filename = re.sub(r'\s+', ' ', filename).strip()
    
    return filename

# ==========================================
# 🛠️ HELPER: BUTTON PARSER (FIXED LAYOUT)
# ==========================================
async def btn_parser(search_id, files, client, offset, a_type=None, a_lang=None, a_qual=None, a_year=None, a_size=None, years=None):
    """
    Ye function buttons ko clean layout mein arrange karega.
    Order: Files -> Navigation -> Filters -> Close
    """
    BUTTONS_PER_PAGE = 10
    total_files = len(files)
    
    # 1. FILES BUTTONS
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot"

    for file in current_files:
        f_id = file.get('link_id')
        raw_name = file.get('file_name', 'Unknown File')
        f_size = get_size(file.get('file_size', 0))
        
        # Clean Name Logic
        f_name = clean_display_name(raw_name)
        if len(f_name) > 30:
            f_name = f_name[:27] + "..."
            
        buttons.append([
            InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )
        ])

    # 2. PAGINATION BUTTONS
    nav_buttons = []
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    # Helper for callback data: filter_id_offset_type_lang_qual_year_size
    def d(off): 
        return f"filter_{search_id}_{off}_{a_type}_{a_lang}_{a_qual}_{a_year}_{a_size}"

    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=d(offset - BUTTONS_PER_PAGE)))

    nav_buttons.append(InlineKeyboardButton(f"📄 {current_page}/{total_pages}", callback_data="pages"))

    if end_index < total_files:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=d(end_index)))

    if nav_buttons:
        buttons.append(nav_buttons)

    # 3. FILTER BUTTONS (Grid Layout)
    # Helper to generate filter callback data
    def f(t=a_type, l=a_lang, q=a_qual, y=a_year, s=a_size):
        return f"filter_{search_id}_0_{t}_{l}_{q}_{y}_{s}"

    # Row A: Type
    type_btns = [
        InlineKeyboardButton(f"{'✅' if a_type=='video' else ''} Videos", callback_data=f(t='video')),
        InlineKeyboardButton(f"{'✅' if a_type=='document' else ''} Docs", callback_data=f(t='document'))
    ]
    # Row B: Language
    lang_btns = [
        InlineKeyboardButton(f"{'✅' if a_lang=='hindi' else ''} Hindi", callback_data=f(l='hindi')),
        InlineKeyboardButton(f"{'✅' if a_lang=='english' else ''} English", callback_data=f(l='english'))
    ]
    # Row C: Quality
    qual_btns = [
        InlineKeyboardButton(f"{'✅' if a_qual=='480p' else ''} 480p", callback_data=f(q='480p')),
        InlineKeyboardButton(f"{'✅' if a_qual=='720p' else ''} 720p", callback_data=f(q='720p')),
        InlineKeyboardButton(f"{'✅' if a_qual=='1080p' else ''} 1080p", callback_data=f(q='1080p'))
    ]
    
    buttons.append(type_btns)
    buttons.append(lang_btns)
    buttons.append(qual_btns)

    # Row D: Years (Top 3 recent)
    if years:
        year_btns = []
        valid_years = sorted([y for y in years if y], reverse=True)[:3] 
        for y in valid_years:
             new_y = None if str(a_year) == str(y) else y
             year_btns.append(InlineKeyboardButton(f"{'✅' if str(a_year) == str(y) else ''} {y}", callback_data=f(y=new_y)))
        if year_btns:
            buttons.append(year_btns)

    # 4. CLOSE
    buttons.append([InlineKeyboardButton("♻️ Close / Delete", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)


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

# Common Search Function
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

    # 🔎 Search in DB
    files = await db.get_search_results(query)
    years = await db.get_unique_years(query)

    # Result Handling
    if not files:
        if is_pm:
            await message.reply_text(f"❌ **No Results Found for:** `{query}`\n\nKripya spelling check karein.")
        return

    # Generate Buttons
    reply_markup = await btn_parser(search_id, files, client, 0, years=years)

    await message.reply_text(
        text=f"🔎 **Results for:** `{query}`\n👇 **Select Filters:**",
        reply_markup=reply_markup,
        quote=True if not is_pm else False
    )

# ==========================================
# 2. CALLBACK HANDLER (Filters & Pagination)
# ==========================================
@Client.on_callback_query(filters.regex(r"^(next|filter)_"))
async def filter_pagination_handler(client: Client, callback: CallbackQuery):
    data = callback.data.split("_")
    try:
        # Data format: action_id_offset_type_lang_qual_year_size
        search_id = int(data[1])
        offset = int(data[2])
        
        def c(v): return None if v == "None" else v
        
        # Safely parse 7 parameters
        a_type = c(data[3]) if len(data) > 3 else None
        a_lang = c(data[4]) if len(data) > 4 else None
        a_qual = c(data[5]) if len(data) > 5 else None
        a_year = c(data[6]) if len(data) > 6 else None
        a_size = c(data[7]) if len(data) > 7 else None

    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired.", show_alert=True)

    # Search with Filters
    files = await db.get_search_results(
        query, 
        file_type=a_type, 
        lang=a_lang, 
        quality=a_qual, 
        year=a_year, 
        size_key=a_size, 
        offset=offset
    )
    years = await db.get_unique_years(query)

    if not files:
        if offset > 0:
            return await callback.answer("⚠️ End of pages.", show_alert=True)
        else:
            await callback.answer("⚠️ No files found for this combo!", show_alert=False)

    # Update Buttons
    new_markup = await btn_parser(
        search_id, files, client, offset, 
        a_type, a_lang, a_qual, a_year, a_size, years=years
    )
    
    text = f"🔎 **Results for:** `{query}`"
    status = []
    if a_type: status.append(f"{a_type.title()}")
    if a_lang: status.append(f"{a_lang.title()}")
    if a_qual: status.append(f"{a_qual}")
    if a_year: status.append(f"{a_year}")
    
    if status: text += f"\n⚙️ **Active:** {', '.join(status)}"

    try:
        await callback.edit_message_text(text=text, reply_markup=new_markup)
    except MessageNotModified:
        pass

# ==========================================
# 3. FILE DELIVERY (Start with File ID)
# ==========================================
@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client, message):
    if len(message.command) < 2 or not message.command[1].startswith("file_"): return
    
    link_id = message.command[1].split("file_", 1)[1]
    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info: 
        return await message.reply("❌ File not found (Deleted or Invalid).")
    
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    
    # Cleaning Name for display
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
# 4. MISC HANDLERS (Pages, Close)
# ==========================================
@Client.on_callback_query(filters.regex("pages"))
async def pages_handler(_, cb): 
    await cb.answer("ℹ️ Current Page", show_alert=True)

@Client.on_callback_query(filters.regex("recheck_menu"))
async def close_handler(_, cb): 
    await cb.message.delete()
