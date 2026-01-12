import math
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# Adjust these imports based on your actual project structure
from database.ia_filterdb import Media
from utils import get_size

# Configuration
BUTTONS_PER_PAGE = 10

async def btn_parser(files: list, offset: int, query: str) -> InlineKeyboardMarkup:
    """
    Generates InlineButtons for files with pagination logic.
    """
    # Calculate total pages
    total_results = len(files)
    total_pages = math.ceil(total_results / BUTTONS_PER_PAGE)
    current_page = (offset // BUTTONS_PER_PAGE) + 1

    # Slice files for the current page
    current_files = files[offset : offset + BUTTONS_PER_PAGE]

    buttons = []

    # 1. File Buttons: [ File Name | Size ]
    for file in current_files:
        # Assuming file object has attributes: file_name, file_size, file_id
        f_caption = f"{file.file_name} | {get_size(file.file_size)}"
        cb_data = f"file#{file.file_id}"
        buttons.append([InlineKeyboardButton(text=f_caption, callback_data=cb_data)])

    # 2. Pagination Buttons
    pagination_row = []

    # Back Button
    if offset >= BUTTONS_PER_PAGE:
        previous_offset = offset - BUTTONS_PER_PAGE
        pagination_row.append(
            InlineKeyboardButton(text="⬅️ Back", callback_data=f"next_{query}_{previous_offset}")
        )

    # Page Counter (Non-clickable or creates a distinct action)
    pagination_row.append(
        InlineKeyboardButton(text=f"Page {current_page}/{total_pages}", callback_data="pages")
    )

    # Next Button
    if (offset + BUTTONS_PER_PAGE) < total_results:
        next_offset = offset + BUTTONS_PER_PAGE
        pagination_row.append(
            InlineKeyboardButton(text="Next ➡️", callback_data=f"next_{query}_{next_offset}")
        )

    if pagination_row:
        buttons.append(pagination_row)

    # 3. Footer Button
    buttons.append([
        InlineKeyboardButton(text="♻️ Wrong Result?", callback_data=f"recheck_menu#{query}")
    ])

    return InlineKeyboardMarkup(buttons)


@Client.on_message(filters.text & filters.group & ~filters.edited)
async def auto_filter(client: Client, message: Message):
    """
    Main Handler: Listens for text in groups and searches the DB.
    """
    query = message.text

    # Basic validation: Ignore very short queries to prevent spam
    if not query or len(query) < 3:
        return

    # Search the database
    # Assuming Media.get_search_results returns a list of file objects
    files = await Media.get_search_results(query)

    if not files:
        # Optional: Send a 'Not found' message or perform a Google search fallback
        # await message.reply_text(f"No results found for '{query}' 😔")
        return

    # Prepare buttons for the first page (offset 0)
    # We pass 'query' to the parser to reconstruct callback data for next pages
    reply_markup = await btn_parser(files, 0, query)

    await message.reply_text(
        text=f"👋 **Hello {message.from_user.mention}**,\n\n"
             f"Found **{len(files)}** results for: `{query}`\n"
             f"👇 Select the file you want:",
        reply_markup=reply_markup,
        quote=True
    )


@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page_handler(client: Client, callback_query: CallbackQuery):
    """
    Handles Pagination (Next/Back buttons).
    Callback Data Format: next_{query}_{offset}
    """
    data = callback_query.data
    
    # Split data. We use maxsplit=2 because the query itself might contain underscores
    # Format: prefix, query, offset
    try:
        _, query, offset_str = data.split("_", 2)
        offset = int(offset_str)
    except ValueError:
        await callback_query.answer("Error processing button data.", show_alert=True)
        return

    # Fetch results again to ensure data consistency
    # (In high-traffic bots, you might cache this, but fetching from DB is standard for simplicity)
    files = await Media.get_search_results(query)

    if not files:
        await callback_query.answer("No files found (database might have changed).", show_alert=True)
        return

    # Generate new buttons for the requested offset
    reply_markup = await btn_parser(files, offset, query)

    try:
        await callback_query.message.edit_text(
            text=f"👋 **Hello {callback_query.from_user.mention}**,\n\n"
                 f"Found **{len(files)}** results for: `{query}`\n"
                 f"👇 Select the file you want:",
            reply_markup=reply_markup
        )
    except Exception as e:
        # Catch "Message is not modified" errors if user clicks same button
        print(f"Pagination Error: {e}")
