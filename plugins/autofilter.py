import math
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# Database aur Utils import
from database.ia_filterdb import Media
from utils import get_size

# Configuration
BUTTONS_PER_PAGE = 10

async def btn_parser(files: list, offset: int, query: str) -> InlineKeyboardMarkup:
    """
    Generates InlineButtons for files with pagination logic.
    """
    total_results = len(files)
    total_pages = math.ceil(total_results / BUTTONS_PER_PAGE)
    current_page = (offset // BUTTONS_PER_PAGE) + 1

    current_files = files[offset : offset + BUTTONS_PER_PAGE]

    buttons = []

    # 1. File Buttons
    for file in current_files:
        f_caption = f"{file['file_name']} | {get_size(file['file_size'])}"
        cb_data = f"file#{file['file_id']}"
        buttons.append([InlineKeyboardButton(text=f_caption, callback_data=cb_data)])

    # 2. Pagination Buttons
    pagination_row = []

    if offset >= BUTTONS_PER_PAGE:
        previous_offset = offset - BUTTONS_PER_PAGE
        pagination_row.append(
            InlineKeyboardButton(text="⬅️ Back", callback_data=f"next_{query}_{previous_offset}")
        )

    pagination_row.append(
        InlineKeyboardButton(text=f"Page {current_page}/{total_pages}", callback_data="pages")
    )

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


# 👇 YAHAN CHANGE KIYA HAI: 'filters.group' hata kar '~filters.private' lagaya hai
@Client.on_message(filters.text & ~filters.private & ~filters.edited)
async def auto_filter(client: Client, message: Message):
    """
    Main Handler: Listens for text in groups and searches the DB.
    """
    query = message.text

    # Validation
    if not query or len(query) < 3:
        return
    
    # Agar message command hai (/start, /filter etc) to ignore karein
    if query.startswith("/"):
        return

    # Database Search
    files = await Media.get_search_results(query)

    if not files:
        return

    # Prepare buttons
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
    """
    data = callback_query.data
    
    try:
        _, query, offset_str = data.split("_", 2)
        offset = int(offset_str)
    except ValueError:
        await callback_query.answer("Error processing button data.", show_alert=True)
        return

    files = await Media.get_search_results(query)

    if not files:
        await callback_query.answer("No files found.", show_alert=True)
        return

    reply_markup = await btn_parser(files, offset, query)

    try:
        await callback_query.message.edit_text(
            text=f"👋 **Hello {callback_query.from_user.mention}**,\n\n"
                 f"Found **{len(files)}** results for: `{query}`\n"
                 f"👇 Select the file you want:",
            reply_markup=reply_markup
        )
    except Exception:
        pass
