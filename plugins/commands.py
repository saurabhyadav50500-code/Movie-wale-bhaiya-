import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db_users
from database.ia_filterdb import db               # Naya import file nikalne ke liye
from utils import check_verification              # Naya import verification check ke liye
from info import ADMINS 

# Logger setup
logger = logging.getLogger(__name__)

# ==================================================================
# 👇 IS BAAR EK RELIABLE HD LINK DALA HAI (Cinema Theme) 👇
START_IMG = "https://images.unsplash.com/photo-1626814026160-2237a95fc5a0?q=80&w=1080&auto=format&fit=crop"
# ==================================================================

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # Agar start payload ke saath aaya hai (link se start hua hai)
    if len(message.command) > 1:
        cmd = message.command[1]
        
        # --- 🔗 HANDLE VERIFICATION RETURN ---
        if cmd.startswith("verify_"):
            try:
                # Format: verify_level_userid_chatid_fileid
                _, level, target_user_id, chat_id, file_link_id = cmd.split("_")
                level, target_user_id, chat_id = int(level), int(target_user_id), int(chat_id)
                
                # Check ki kisi aur ne to link share nahi kiya
                if message.from_user.id != target_user_id:
                    return await message.reply("❌ Ye link aapke liye nahi hai. Kripya bot me dobara request karein.")
                    
                settings = await db_users.get_group_shortener(chat_id)
                verify_time = settings.get("verify_time", 86400) if settings else 86400
                
                # Update status in DB
                await db_users.update_verify_status(target_user_id, chat_id, level, verify_time)
                
                # Check agar next level baaki hai
                is_verified, markup = await check_verification(client, target_user_id, chat_id, file_link_id)
                
                if not is_verified:
                    return await message.reply(
                        f"✅ Level {level} Completed!\n\n⚠️ Aage ki file receive karne ke liye next level verify karein.",
                        reply_markup=markup
                    )
                else:
                    s_msg = await message.reply("🎉 **All Verifications Completed!** \n\nSending your file now...")
                    
                    # File bhej do
                    file_info = await db.get_file_by_link_id(file_link_id)
                    if file_info:
                        await client.send_cached_media(
                            message.from_user.id, 
                            file_info['file_id'], 
                            caption=file_info['caption'] or ""
                        )
                        await s_msg.delete()
                    return
            except Exception as e:
                return await message.reply("❌ Invalid or Expired Verification Link.")
                
        # Agar 'file_' command hai to autofilter handler usko handle kar lega isliye yahan se return karo
        if cmd.startswith("file_"):
            return

    # =========================================================
    # --- NORMAL START MESSAGE (Aapka Purana Logic) ---
    # =========================================================
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

    # 3. Welcome Text
    welcome_text = (
        f"**Hello {first_name}!** 👋\n\n"
        f"Main Movies Search Bot hoon. 🎬\n"
        f"Koi bhi Movie/Series ka naam likh kar bhejo, main file dhoond dunga."
    )

    # --- ADMIN PEHCHAN (BOSS LOGIC) ---
    if user_id in ADMINS:
        welcome_text += "\n\n👑 **Welcome Boss!** Aap Admin hain. Aap `/index`, `/stats`, `/broadcast` jaise commands use kar sakte hain."

    # 4. Photo ke saath Message bhejo
    try:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=START_IMG,
            caption=welcome_text,
            reply_markup=buttons,
            reply_to_message_id=message.id
        )
    except Exception as e:
        # Agar photo ab bhi fail hui, to logs me error dikhega
        print(f"❌ Message Send Error: {e}", flush=True)
        # Fallback to text
        await message.reply_text(welcome_text, reply_markup=buttons)


# --- CALLBACKS (About & Status) ---
# Note: Photo message edit karne ke liye 'edit_caption' use hota hai
@Client.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback):
    await callback.answer()
    try:
        await callback.message.edit_caption(
            caption=(
                "ℹ️ **About Me**\n\n"
                "Main ek Advanced Auto-Filter Bot hoon.\n"
                "Mera kaam hai Groups/Channel se files index karna aur user ko dena.\n\n"
                "Developed with ❤️ by You."
            ),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
        )
    except:
        # Agar photo nahi thi (text msg tha), to normal edit karo
        await callback.message.edit_text(
            "ℹ️ **About Me**\n\nText Mode...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
        )

@Client.on_callback_query(filters.regex("stats_callback"))
async def stats_callback(client, callback):
    await callback.answer()
    try:
        await callback.message.edit_caption(
            caption="📉 **Bot Status**\n\nBot is Running Smoothly! ✅",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
        )
    except:
        await callback.message.edit_text(
            "📉 **Bot Status**\n\nBot is Running Smoothly! ✅",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="recheck_menu")]])
        )

@Client.on_callback_query(filters.regex("recheck_menu"))
async def home_callback(client, callback):
    await callback.answer()
    first_name = callback.from_user.first_name
    
    # Wapas original Menu Text
    text = (
        f"**Hello {first_name}!** 👋\n\n"
        f"Main Movies Search Bot hoon. 🎬\n"
        f"Koi bhi Movie/Series ka naam likh kar bhejo, main file dhoond dunga."
    )
    if callback.from_user.id in ADMINS:
        text += "\n\n👑 **Welcome Boss!** Aap Admin hain."

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"http://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("ℹ️ About", callback_data="about_section"), InlineKeyboardButton("📉 Status", callback_data="stats_callback")]
    ])
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=buttons)
    except:
        await callback.message.edit_text(text=text, reply_markup=buttons)
