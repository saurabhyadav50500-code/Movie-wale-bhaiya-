import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.ia_filterdb import db

# --- Helper Function for Pagination Buttons ---
def get_pagination_nodes(current_page, total_pages, query):
    buttons = []
    
    # Back Button (Agar 1st page par nahi hain)
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"search#{query}#{current_page - 1}"))
    
    # Page Indicator
    buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="pages"))
    
    # Next Button (Agar last page par nahi hain)
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"search#{query}#{current_page + 1}"))
    
    return [buttons]

# --- MAIN SEARCH HANDLER (TEXT) ---
@Client.on_message(filters.text & filters.private & ~filters.command(["start", "index", "batch"]))
async def search_handler(bot: Client, message: Message):
    """
    Jab user koi movie/series ka naam likhega (bina /command ke).
    """
    query = message.text
    if len(query) < 3:
        return await message.reply_text("⚠️ Kam se kam 3 characters likhein search karne ke liye.")

    # Status message bhejein
    status = await message.reply_text("🔎 Searching...")
    
    # Database se search karein
    files = await db.get_search_results(query)
    
    if not files:
        return await status.edit(f"❌ '{query}' ke liye koi file nahi mili.")
    
    # --- PAGE 1 DISPLAY LOGIC ---
    # Har page par 10 files dikhayenge
    FILES_PER_PAGE = 10
    total_files = len(files)
    
    # List ko slice karein (0 se 10 tak)
    page_files = files[0:FILES_PER_PAGE]
    
    # Buttons banayein (File Links)
    buttons = []
    bot_username = (await bot.get_me()).username
    
    for file in page_files:
        # Har file ka direct start link
        file_link = f"https://t.me/{bot_username}?start={file['link_id']}"
        buttons.append([InlineKeyboardButton(f"📂 {file['file_name']}", url=file_link)])

    # Pagination Buttons add karein (Next/Back)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    
    if total_pages > 1:
        buttons.extend(get_pagination_nodes(0, total_pages, query))

    # Result bhejein
    text = f"**Found {total_files} results for:** `{query}`\n\n👇 **Niche click karke download karein:**"
    await status.edit(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- CALLBACK QUERY HANDLER (NEXT/BACK BUTTONS) ---
@Client.on_callback_query(filters.regex(r"^search#"))
async def search_pagination_callback(bot: Client, query):
    """
    Jab user Next ya Back button dabayega.
    Callback Data Format: search#query_string#page_number
    """
    _, search_query, page_str = query.data.split("#")
    page = int(page_str)
    
    # Wapas search karein (Cache use kar sakte hain, par abhi direct DB call simple hai)
    files = await db.get_search_results(search_query)
    
    if not files:
        return await query.answer("Results expire ho gaye, dobara search karein.", show_alert=True)

    FILES_PER_PAGE = 10
    total_files = len(files)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    
    # Start aur End index calculate karein
    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = files[start:end]
    
    # Buttons regenerate karein
    buttons = []
    bot_username = (await bot.get_me()).username
    
    for file in page_files:
        file_link = f"https://t.me/{bot_username}?start={file['link_id']}"
        buttons.append([InlineKeyboardButton(f"📂 {file['file_name']}", url=file_link)])

    # Pagination Buttons
    if total_pages > 1:
        buttons.extend(get_pagination_nodes(page, total_pages, search_query))
        
    # Message Edit karein
    text = f"**Found {total_files} results for:** `{search_query}`\n**Page:** {page + 1}/{total_pages}"
    
    try:
        await query.message.edit(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        pass # Agar message same hai to error ignore karein

# --- START HANDLER WITH LINK ID ---
@Client.on_message(filters.command("start"))
async def start_handler(bot: Client, message: Message):
    # Check if parameter exists (e.g., /start link_id)
    if len(message.command) > 1:
        link_id = message.command[1]
        file_doc = await db.get_file_by_link_id(link_id)
        
        if not file_doc:
            return await message.reply_text("❌ File nahi mili ya delete ho gayi hai.")
        
        try:
            await message.reply_cached_media(
                file_id=file_doc['file_id'],
                caption=file_doc['caption'] or f"**{file_doc['file_name']}**"
            )
        except Exception as e:
            await message.reply_text(f"Error sending file: {e}")
    else:
        await message.reply_text("👋 **Welcome!**\n\nKoi bhi **Movie ya Series ka naam** likh kar bhejein search karne ke liye.")
