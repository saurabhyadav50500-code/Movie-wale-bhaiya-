import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.ia_filterdb import db

# --- Helper Function for Pagination Buttons ---
def get_pagination_nodes(current_page, total_pages, query):
    buttons = []
    
    # Back Button
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"search#{query}#{current_page - 1}"))
    
    # Page Indicator
    buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="pages"))
    
    # Next Button
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"search#{query}#{current_page + 1}"))
    
    return [buttons]

# --- MAIN SEARCH HANDLER (AUTO FILTER) ---
# Ye ab Group aur Private dono me chalega
@Client.on_message(filters.text & ~filters.command(["start", "index", "batch"]))
async def search_handler(bot: Client, message: Message):
    """
    Auto Filter Logic:
    1. Check message text.
    2. Search in DB.
    3. If found -> Send Buttons.
    4. If not found -> Group me silent rahega, Private me 'Not Found' bolega.
    """
    query = message.text
    
    # Agar query bahut choti hai to ignore karein
    if len(query) < 3:
        return 

    # Agar private chat hai to "Searching" status bhejein
    # Group me status nahi bhejenge taaki spam na ho
    status = None
    if message.chat.type == list(filters.private)[0]: # Check if private
        status = await message.reply_text("🔎 Searching...")

    # Database Search
    files = await db.get_search_results(query)
    
    # --- NO RESULTS HANDLING ---
    if not files:
        if status: # Sirf Private chat me error dikhayein
            await status.edit(f"❌ No files found for '{query}'.")
        return # Group me kuch mat karo agar file nahi mili

    # --- RESULTS FOUND ---
    
    # Page 1 Setup
    FILES_PER_PAGE = 10
    total_files = len(files)
    page_files = files[0:FILES_PER_PAGE]
    
    # Buttons Create Karna
    buttons = []
    bot_username = (await bot.get_me()).username
    
    for file in page_files:
        # Deep Link: Button click karne par user PM me jayega file lene
        file_link = f"https://t.me/{bot_username}?start={file['link_id']}"
        
        # Button Text: [File Name] (File Size)
        # Size ko human readable banane ke liye simple logic ya library use kar sakte hain
        # Abhi ke liye simple naam rakhte hain
        buttons.append([InlineKeyboardButton(f"📂 {file['file_name']}", url=file_link)])

    # Pagination Buttons
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    if total_pages > 1:
        buttons.extend(get_pagination_nodes(0, total_pages, query))

    # Message Text
    text = (
        f"👋 **Hello {message.from_user.mention}**\n\n"
        f"🔍 **Query:** `{query}`\n"
        f"🗃️ **Total Results:** `{total_files}`\n\n"
        "👇 **Click below to get files:**"
    )

    # Message Send Karna
    if status:
        await status.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        # Group me naya message
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- PAGINATION CALLBACK (Next/Back) ---
@Client.on_callback_query(filters.regex(r"^search#"))
async def search_pagination_callback(bot: Client, query):
    _, search_query, page_str = query.data.split("#")
    page = int(page_str)
    
    files = await db.get_search_results(search_query)
    
    if not files:
        return await query.answer("Links expired. Please search again.", show_alert=True)

    FILES_PER_PAGE = 10
    total_files = len(files)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    
    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = files[start:end]
    
    buttons = []
    bot_username = (await bot.get_me()).username
    
    for file in page_files:
        file_link = f"https://t.me/{bot_username}?start={file['link_id']}"
        buttons.append([InlineKeyboardButton(f"📂 {file['file_name']}", url=file_link)])

    if total_pages > 1:
        buttons.extend(get_pagination_nodes(page, total_pages, search_query))
        
    text = (
        f"👋 **Hello {query.from_user.mention}**\n\n"
        f"🔍 **Query:** `{search_query}`\n"
        f"🗃️ **Total Results:** `{total_files}`\n"
        f"📄 **Page:** {page + 1}/{total_pages}"
    )
    
    try:
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        pass


# --- START HANDLER (Retrieves File) ---
@Client.on_message(filters.command("start"))
async def start_handler(bot: Client, message: Message):
    if len(message.command) > 1:
        link_id = message.command[1]
        file_doc = await db.get_file_by_link_id(link_id)
        
        if not file_doc:
            return await message.reply_text("❌ File not found.")
        
        try:
            await message.reply_cached_media(
                file_id=file_doc['file_id'],
                caption=file_doc['caption'] or f"**{file_doc['file_name']}**"
            )
        except Exception as e:
            await message.reply_text(f"Error: {e}")
    else:
        # Private chat me hi welcome message dikhayein
        if message.chat.type == list(filters.private)[0]:
            await message.reply_text("👋 **Auto Filter Bot!**\n\nAdd me to your group and make me Admin.")
