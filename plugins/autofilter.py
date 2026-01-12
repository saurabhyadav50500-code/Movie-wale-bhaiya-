import math
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified
from database.ia_filterdb import db
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

async def btn_parser(query: str, files: list, client: Client, offset: int = 0):
    """
    Generates the InlineKeyboardMarkup with URL buttons (Deep Link) and pagination.
    """
    # 1. Slice the list for the current page
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []

    # Bot ka Username chahiye URL banane ke liye
    # (Hum isse client.me.username se le rahe hain)
    # Agar client.me load nahi hai to safe fallback
    bot_username = client.me.username if client.me else "temp_bot_username"

    # 2. Create File Buttons: [ File Name | Size ] -> URL Button
    for file in current_files:
        f_id = file.get('link_id') 
        f_name = file.get('file_name', 'Unknown File')
        f_size = get_size(file.get('file_size', 0))
        
        # Truncate long filenames
        if len(f_name) > 30:
            f_name = f_name[:27] + "..."
            
        # URL Button banayenge (PM mein redirect karne ke liye)
        # Format: https://t.me/BotUsername?start=file_LINKID
        buttons.append(
            [InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )]
        )

    # 3. Pagination Logic
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

    # 4. Footer Button
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
    """
    Catches text messages in groups and searches the database.
    """
    query = message.text
    
    if not query or len(query) < 2 or query.startswith("/"):
        return

    # Bot ki identity load karein (Username ke liye zaroori hai)
    if not client.me:
        await client.get_me()

    files = await db.get_search_results(query)

    if not files:
        return 

    # 'client' ko pass kar rahe hain taaki username mil sake
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

    # Bot identity check
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
# 3. FILE DELIVERY HANDLER (PM Only)
# ==========================================
# Jab user link par click karke PM mein aayega -> /start file_xyz123

@Client.on_message(filters.command("start") & filters.private & filters.regex("file_"))
async def file_delivery_handler(client: Client, message: Message):
    """
    Handles the Deep Link start command to deliver the file.
    """
    try:
        # /start file_xyz123 -> extract 'xyz123'
        # message.text looks like: "/start file_abc123"
        if len(message.command) < 2:
            return

        link_id = message.command[1].split("file_", 1)[1]
    except IndexError:
        return await message.reply("❌ Invalid Link")

    # Fetch file details from DB
    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info:
        return await message.reply("❌ File not found (Deleted).")

    # Status Message
    msg = await message.reply("📂 **Sending File... Please wait.**", quote=True)

    try:
        # Send the file
        await client.send_cached_media(
            chat_id=message.from_user.id,
            file_id=file_info['file_id'],
            caption=file_info['caption'] or "",
        )
        await msg.delete() # Loading message delete kar do
    except Exception as e:
        print(f"Send File Error: {e}")
        await msg.edit(f"❌ Error sending file: {e}")


# ==========================================
# 4. CLOSE BUTTON HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client: Client, callback: CallbackQuery):
    await callback.message.delete()
