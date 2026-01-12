import math
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import MessageNotModified
from database.ia_filterdb import db
from utils import get_size

# --- CONFIGURATION ---
BUTTONS_PER_PAGE = 10

async def btn_parser(query: str, files: list, offset: int = 0):
    """
    Generates the InlineKeyboardMarkup with file buttons and pagination.
    """
    # 1. Slice the list for the current page
    end_index = offset + BUTTONS_PER_PAGE
    current_files = files[offset:end_index]
    
    buttons = []

    # 2. Create File Buttons: [ File Name | Size ]
    for file in current_files:
        # Use link_id for callbacks (shorter and safer)
        f_id = file.get('link_id') 
        f_name = file.get('file_name', 'Unknown File')
        f_size = get_size(file.get('file_size', 0))
        
        # Truncate long filenames (max 30 chars)
        if len(f_name) > 30:
            f_name = f_name[:27] + "..."
            
        buttons.append(
            [InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                callback_data=f"file#{f_id}"
            )]
        )

    # 3. Pagination Logic
    total_files = len(files)
    total_pages = math.ceil(total_files / BUTTONS_PER_PAGE)
    current_page = math.ceil(offset / BUTTONS_PER_PAGE) + 1
    
    nav_buttons = []

    # Back Button (Only if not on first page)
    if offset >= BUTTONS_PER_PAGE:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data=f"next_{query}_{offset - BUTTONS_PER_PAGE}"
            )
        )

    # Page Counter (Visual only)
    nav_buttons.append(
        InlineKeyboardButton(
            text=f"Page {current_page}/{total_pages}",
            callback_data="pages" 
        )
    )

    # Next Button (Only if more files exist)
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
@Client.on_message(filters.text & filters.group & ~filters.edited)
async def auto_filter(client: Client, message: Message):
    """
    Catches text messages in groups and searches the database.
    """
    query = message.text
    
    # Ignore short queries or commands
    if len(query) < 2 or query.startswith("/"):
        return

    # Search Database
    files = await db.get_search_results(query)

    if not files:
        return # No result found, stay silent

    # Generate Buttons for the first page (offset 0)
    reply_markup = await btn_parser(query, files, offset=0)

    await message.reply_text(
        text=f"🔎 **Found {len(files)} results for:** `{query}`",
        reply_markup=reply_markup,
        quote=True
    )


# ==========================================
# 2. PAGINATION HANDLER (Next/Back)
# ==========================================
@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page_handler(client: Client, callback: CallbackQuery):
    """
    Handles Pagination (Next/Back buttons).
    Callback Data format: next_{query}_{offset}
    """
    data = callback.data
    
    try:
        # Parsing using rsplit to handle movie names with underscores
        # "next_Iron_Man_10" -> prefix="next_Iron_Man", str_offset="10"
        prefix_query, str_offset = data.rsplit("_", 1)
        
        # Remove "next_" from the beginning
        query = prefix_query.split("_", 1)[1]
        offset = int(str_offset)
    except (IndexError, ValueError):
        return await callback.answer("❌ Error parsing pagination data.", show_alert=True)

    # Re-fetch results
    files = await db.get_search_results(query)

    if not files:
        return await callback.answer("❌ Search results expired.", show_alert=True)

    # Generate new buttons
    new_markup = await btn_parser(query, files, offset=offset)

    try:
        await callback.edit_message_reply_markup(reply_markup=new_markup)
    except MessageNotModified:
        pass # User clicked same button twice, ignore error
    except Exception as e:
        print(f"Pagination Error: {e}")


# ==========================================
# 3. FILE SENDING HANDLER (On Button Click)
# ==========================================
@Client.on_callback_query(filters.regex(r"^file#"))
async def file_click_handler(client: Client, callback: CallbackQuery):
    """
    Handles clicking on a file button to send the file.
    Data format: file#{link_id}
    """
    try:
        link_id = callback.data.split("#", 1)[1]
    except IndexError:
        return await callback.answer("❌ Invalid Request")

    # Fetch file details from DB
    file_info = await db.get_file_by_link_id(link_id)
    
    if not file_info:
        return await callback.answer("❌ File not found (Deleted).", show_alert=True)

    await callback.answer("📂 Sending File...", show_alert=False)

    try:
        # Send the file
        await client.send_cached_media(
            chat_id=callback.message.chat.id,
            file_id=file_info['file_id'],
            caption=file_info['caption'] or "",
            reply_to_message_id=callback.message.reply_to_message.id if callback.message.reply_to_message else None
        )
    except Exception as e:
        print(f"Send File Error: {e}")
        await callback.answer("❌ Error sending file. Make sure I am Admin.", show_alert=True)


# ==========================================
# 4. CLOSE BUTTON HANDLER
# ==========================================
@Client.on_callback_query(filters.regex(r"^recheck_menu"))
async def close_handler(client: Client, callback: CallbackQuery):
    await callback.message.delete()
