import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users

# Logger setup
logger = logging.getLogger(__name__)

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # Logs me print karega taaki humein pata chale command aya
    print(f"➡️ Start Command From: {message.from_user.first_name}", flush=True)

    # Agar '/start file_id' hai (File mangi hai), to ye handler ignore karega
    # (Kyunki ye kaam autofilter.py karega)
    if len(message.command) > 1:
        return 

    # 1. User ko Database me add karein (Safety ke saath)
    try:
        await db_users.add_user(message.from_user.id, message.from_user.first_name)
    except Exception as e:
        print(f"❌ DB Error in Start: {e}", flush=True)
        # Error aane par bhi bot rukega nahi, aage badhega

    # 2. Buttons Banao
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])

    # 3. Message bhejo
    try:
        await message.reply_text(
            text=f"**Hello {message.from_user.first_name}!** 👋\n\nMain Movies Search Bot hoon. \nKoi bhi Movie/Series ka naam likh kar bhejo, main file dhoond dunga.",
            reply_markup=buttons,
            quote=True
        )
        print("✅ Start Reply Sent!", flush=True)
    except Exception as e:
        print(f"❌ Message Send Error: {e}", flush=True)

# --- CALLBACKS (About & Status) ---
@Client.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback):
    await callback.answer()
    await callback.message.edit_text(
        "ℹ️ **About Me**\n\n"
        "Main ek Advanced Auto-Filter Bot hoon.\n"
        "Mera kaam hai Groups/Channel se files index karna aur user ko dena.\n\n"
        "Developed with ❤️ by You."
    )

@Client.on_callback_query(filters.regex("stats_callback"))
async def stats_callback(client, callback):
    await callback.answer()
    await callback.message.edit_text("📉 **Stats**\n\nAbhi database connect ho raha hai...")
