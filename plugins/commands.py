import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users
from info import ADMINS 

# Logger setup
logger = logging.getLogger(__name__)

# ==================================================================
# 👇 MAINE YE MAST PHOTO LAGA DI HAI 👇
START_IMG = "https://graph.org/file/4b5258d4a974b7c1266a1.jpg"
# ==================================================================

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # Agar '/start file_id' hai (File mangi hai), to ignore karo
    if len(message.command) > 1:
        return 

    user_id = message.from_user.id
    first_name = message.from_user.first_name

    # 1. User ko Database me add karein
    try:
        await db_users.add_user(user_id, first_name)
    except Exception as e:
        logger.error(f"❌ DB Error in Start: {e}")

    # 2. Buttons Banao
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])

    # 3. Welcome Text (Wahi Mast Wala)
    welcome_text = (
        f"**Hello {first_name}!** 👋\n\n"
        f"Main Movies Search Bot hoon. 🎬\n"
        f"Koi bhi Movie/Series ka naam likh kar bhejo, main file dhoond dunga."
    )

    # --- ADMIN PEHCHAN (BOSS LOGIC) ---
    # Agar message bhejne wala Admin/Owner hai, to extra line add karo
    if user_id in ADMINS:
        welcome_text += "\n\n👑 **Welcome Boss!** Aap Admin hain. Aap `/index`, `/stats`, `/broadcast` jaise commands use kar sakte hain."

    # 4. Photo ke saath Message bhejo
    try:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=START_IMG,           # Meri pasand ki photo
            caption=welcome_text,      # Aapka pasandeeda text
            reply_markup=buttons,
            reply_to_message_id=message.id
        )
    except Exception as e:
        print(f"❌ Message Send Error: {e}", flush=True)
        # Agar photo load na ho paye, to kam se kam text bhej dega
        await message.reply_text(welcome_text, reply_markup=buttons)


# --- CALLBACKS (About & Status) ---
@Client.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback):
    await callback.answer()
    await callback.message.edit_caption(
        caption=(
            "ℹ️ **About Me**\n\n"
            "Main ek Advanced Auto-Filter Bot hoon.\n"
            "Mera kaam hai Groups/Channel se files index karna aur user ko dena.\n\n"
            "Developed with ❤️ by You."
        ),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
    )

@Client.on_callback_query(filters.regex("stats_callback"))
async def stats_callback(client, callback):
    await callback.answer()
    await callback.message.edit_caption(
        caption="📉 **Bot Status**\n\nBot is Running Smoothly! ✅",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
    )
