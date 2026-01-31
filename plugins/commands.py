from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # Agar start ke saath kuch aur text hai (jaise deep link), to Autofilter handle karega
    if len(message.command) > 1:
        return 
    
    # User ko database me add karein
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    
    # Bot ka username nikalein (Add to group link ke liye)
    bot_info = await client.get_me()
    bot_username = bot_info.username

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])
    
    await message.reply_text(
        text=f"**Hello {message.from_user.first_name}!** 👋\n\nMain Movies Search Bot hoon. Naam bhejo, main file dhoond dunga.",
        reply_markup=buttons
    )
