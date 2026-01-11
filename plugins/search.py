import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.ia_filterdb import db

# --- Helper Function for Pagination Buttons ---
def get_pagination_nodes(current_page, total_pages, query):
    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"search#{query}#{current_page - 1}"))
    buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="pages"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"search#{query}#{current_page + 1}"))
    return [buttons]

# --- MAIN SEARCH HANDLER ---
@Client.on_message(filters.text & ~filters.command(["start", "index", "batch"]))
async def search_handler(bot: Client, message: Message):
    """
    Search Logic Updated:
    - /search command -> Always reply (Found or Not Found).
    - Normal Text -> Reply only if Found (Silent if not found).
    """
    
    query = message.text
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    
    # Flag to check if user explicitly used a command or tag
    explicit_command = False 

    # CASE 1: Check for /search or /find command
    if query.startswith("/") and ( "search" in query or "find" in query):
        explicit_command = True # User wants an answer
        split_text = query.split(" ", 1)
        if len(split_text) > 1:
            query = split_text[1] # Actual movie name
        else:
            # Agar user ne sirf "/search" likha bina query ke
            return await message.reply("⚠️ Likhne ka tareeka: `/search MovieName`")

    # CASE 2: Check for Mentions (@BotName query)
    elif f"@{bot_username}" in query:
        explicit_command = True # User tagged bot, so they expect an answer
        query = query.replace(f"@{bot_username}", "").strip()
        
    # CASE 3: Normal Text (Auto Filter)
    # explicit_command False rahega
    
    # --- Validations ---
    if len(query) < 3:
        return 

    # --- Database Search ---
    # Private chat me hamesha status dikhayein
    status = None
    if message.chat.type == list(filters.private)[0]: 
        status = await message.reply_text("🔎 Searching...")

    files = await db.get_search_results(query)
    
    # --- NO RESULTS HANDLING (Fixed) ---
    if not files:
        if status: 
            await status.edit(f"❌ No files found for '{query}'.")
        elif explicit_command:
            # Agar Group me COMMAND use kiya hai, to Reply karein
            await message.reply_text(f"❌ No files found for '{query}'.")
        return # Agar normal text tha aur result nahi mila, to Silent rahein

    # --- RESULTS FOUND ---
    FILES_PER_PAGE = 10
    total_files = len(files)
    page_files = files[0:FILES_PER_PAGE]
    
    buttons = []
    
    for file in page_files:
        file_link = f"https://t.me/{bot_username}?start={file['link_id']}"
        buttons.append([InlineKeyboardButton(f"📂 {file['file_name']}", url=file_link)])

    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    if total_pages > 1:
        buttons.extend(get_pagination_nodes(0, total_pages, query))

    text = (
        f"👋 **Hello {message.from_user.mention}**\n\n"
        f"🔍 **Query:** `{query}`\n"
        f"🗃️ **Total Results:** `{total_files}`\n\n"
        "👇 **Click below to get files:**"
    )

    if status:
        await status.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- PAGINATION & START HANDLER ---
# (Ye neeche wala code same rahega, copy-paste karein agar hat gaya ho)
@Client.on_callback_query(filters.regex(r"^search#"))
async def search_pagination_callback(bot: Client, query):
    _, search_query, page_str = query.data.split("#")
    page = int(page_str)
    
    files = await db.get_search_results(search_query)
    
    if not files:
        return await query.answer("Links expired.", show_alert=True)

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

@Client.on_message(filters.command("start"))
async def start_handler(bot: Client, message: Message):
    if len(message.command) > 1:
        link_id = message.command[1]
        file_doc = await db.get_file_by_link_id(link_id)
        if file_doc:
            await message.reply_cached_media(
                file_id=file_doc['file_id'],
                caption=file_doc['caption'] or f"**{file_doc['file_name']}**"
            )
        else:
            await message.reply_text("❌ File not found.")
    else:
        if message.chat.type == list(filters.private)[0]:
            await message.reply_text("👋 **Welcome!**\nUse /search <movie_name> to find files.")
