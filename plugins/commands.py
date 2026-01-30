from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1: return # Autofilter handle karega deep links ko
    
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])
    
    await message.reply_text(
        text=f"**Hello {message.from_user.first_name}!** 👋\n\nMain Movies Search Bot hoon. Naam bhejo, main file dhoond dunga.",
        reply_markup=buttons
    )
