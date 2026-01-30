# plugins/commands.py
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # Agar deep link hai (e.g., file download), to autofilter handle karega
    if len(message.command) > 1: 
        return 
    
    # User ko database mein add karein
    await db_users.add_user(message.from_user.id, message.from_user.first_name)
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])
    
    # Bot ka photo aur welcome text
    IMG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/480px-Python-logo-notext.svg.png" # Yahan apna link dalein
    
    await message.reply_photo(
        photo=IMG_URL,
        caption=f"**Namaste {message.from_user.first_name}!** 🙏\n\nMain ek **Auto Filter Bot** hoon.\n\nMujhe movie ka naam bhejein (bhayi spelling galat bhi hogi to chalega!), main dhoond dunga.",
        reply_markup=buttons
    )

@Client.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback):
    await callback.answer()
    await callback.message.edit_text(
        "**🤖 About Me**\n\n"
        "Main MongoDB Atlas Search use karta hoon taaki spelling mistakes hone par bhi sahi movie mile.\n"
        "• **Language:** Python 3\n"
        "• **Database:** MongoDB\n"
        "• **Developer:** You"
    )
