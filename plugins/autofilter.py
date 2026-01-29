import asyncio
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message
from pyrogram.errors import MessageNotModified

from database.ia_filterdb import db
from database.analytics import analytics
from database.users_chats_db import db_users
from utils import btn_parser

# ==========================================
# 1. MAIN TEXT HANDLER
# ==========================================
@Client.on_message(filters.text & filters.group)
async def auto_filter(client: Client, message: Message):
    query = message.text
    if not query or len(query) < 2 or query.startswith("/"): return
    if not client.me: await client.get_me()

    # Settings & Analytics
    await db_users.get_group_status(message.chat.id)
    search_id = await db.save_search_query(query, message.from_user.id)
    asyncio.create_task(analytics.log_search(message.text, query, 0, message.from_user.id, message.chat.id))

    if not search_id: return await message.reply("❌ Database Error.")

    # Search (No Filters)
    files = await db.get_search_results(query)

    if not files: return 

    # Generate Buttons
    reply_markup = await btn_parser(search_id, files, client, 0)

    await message.reply_text(
        text=f"🔎 **Results for:** `{query}`\n👇 **Select Filters:**",
        reply_markup=reply_markup,
        quote=True
    )

# ==========================================
# 2. MASTER CALLBACK HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^(next|filter)_"))
async def filter_pagination_handler(client: Client, callback: CallbackQuery):
    """
    Handles ALL Clicks (Next/Back, Type, Lang, Qual, Year, Size)
    Format: action_id_off_type_lang_qual_year_size
    """
    data = callback.data.split("_")
    
    try:
        # data[0] = action (ignored)
        search_id = int(data[1])
        offset = int(data[2])
        
        # Helper to clean "None" strings
        def c(v): return None if v == "None" else v
        
        # Parsing 5 Params safely
        a_type = c(data[3]) if len(data) > 3 else None
        a_lang = c(data[4]) if len(data) > 4 else None
        a_qual = c(data[5]) if len(data) > 5 else None
        a_year = c(data[6]) if len(data) > 6 else None
        a_size = c(data[7]) if len(data) > 7 else None

    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing data.", show_alert=True)

    # 1. Get Query
    query = await db.get_search_query(search_id)
    if not query:
        return await callback.answer("❌ Search Expired.", show_alert=True)

    # 2. DB Search (All Filters)
    files = await db.get_search_results(
        query, 
        file_type=a_type,
        lang=a_lang, 
        quality=a_qual, 
        year=a_year, 
        size_key=a_size,
        offset=offset
    )

    # 3. Handle Empty Results
    if not files:
        if offset > 0:
            return await callback.answer("⚠️ End of pages.", show_alert=True)
        else:
            await callback.answer("⚠️ No files found for this combo!", show_alert=False)

    # 4. Generate New Buttons
    new_markup = await btn_parser(
        search_id, files, client, offset, 
        a_type, a_lang, a_qual, a_year, a_size
    )
    
    # 5. Status Text
    status = []
    if a_type: status.append(f"{a_type.title()}")
    if a_lang: status.append(f"{a_lang.title()}")
    if a_qual: status.append(f"{a_qual}")
    if a_year: status.append(f"{a_year}")
    if a_size: status.append(f"{a_size}")
    
    text = f"🔎 **Results for:** `{query}`"
    if status: text += f"\n⚙️ **Active:** {', '.join(status)}"

    try:
        await callback.edit_message_text(text=text, reply_markup=new_markup)
    except MessageNotModified:
        pass

@Client.on_message(filters.command("start") & filters.private, group=-1)
async def file_delivery_handler(client, message):
    if len(message.command) < 2 or not message.command[1].startswith("file_"): return
    link_id = message.command[1].split("file_", 1)[1]
    file_info = await db.get_file_by_link_id(link_id)
    if not file_info: return await message.reply("❌ File not found.")
    
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    s_msg = await message.reply("📂 **Sending File...**")
    try:
        await client.send_cached_media(message.from_user.id, file_info['file_id'], caption=file_info['caption'])
        await s_msg.delete()
    except Exception as e:
        await s_msg.edit(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("pages"))
async def pages_handler(_, cb): await cb.answer("Current Page", show_alert=True)

@Client.on_callback_query(filters.regex("recheck_menu"))
async def close_handler(_, cb): await cb.message.delete()
