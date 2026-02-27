import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# Ab hum DummyDB ki jagah apna real MongoDB connection use karenge
from database.users_chats_db import db_users

# ==========================================
# 🧠 STATE TRACKER FOR INPUT
# ==========================================
# Ye track karega ki kaunsa user kis group ke kis slot ke liye input de raha hai
# Naya format: {"chat_id": chat_id, "slot": slot, "type": "api" ya "time"}
AWAITING_INPUT = {}  

# ==========================================
# 🛠️ HELPER: CHECK ADMIN
# ==========================================
async def is_admin(client, chat_id, user_id):
    if chat_id == user_id: # Private Message
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except:
        return False

# ==========================================
# 🎨 UI GENERATORS
# ==========================================
async def get_main_settings_ui(chat_id):
    """Main Menu showing all 3 slots and Mode"""
    settings = await db_users.get_group_shortener_settings(chat_id)
    mode = settings.get("mode", "smart").capitalize()

    buttons = [
        [InlineKeyboardButton("⚙️ Shortener Slot 1", callback_data=f"short_menu_{chat_id}_1")],
        [InlineKeyboardButton("⚙️ Shortener Slot 2", callback_data=f"short_menu_{chat_id}_2")],
        [InlineKeyboardButton("⚙️ Shortener Slot 3", callback_data=f"short_menu_{chat_id}_3")],
        [InlineKeyboardButton(f"🔄 Verification Mode: {mode}", callback_data=f"short_mode_{chat_id}")],
        [InlineKeyboardButton("❌ Close", callback_data="short_close")]
    ]
    text = (
        "⚙️ **Advanced Shortener Settings**\n\n"
        f"**Current Mode:** `{mode}`\n\n"
        "Select a slot below to View, Edit or Disable the URL shortener for this chat."
    )
    return text, InlineKeyboardMarkup(buttons)

async def get_slot_ui(chat_id, slot):
    """Sub-menu showing details of a specific slot"""
    settings = await db_users.get_group_shortener_settings(chat_id)
    slot_data = settings["slots"].get(str(slot), {})
    
    site = slot_data.get("site", "")
    api = slot_data.get("api", "")
    time_sec = slot_data.get("time", 86400)
    time_hr = time_sec // 3600

    status = "🟢 Active" if site and api else "🔴 Disabled"
    site_disp = site if site else "None"
    api_disp = api[:5] + "..." if api else "None"

    text = (
        f"🔗 **Shortener Settings (Slot {slot})**\n\n"
        f"**Status:** {status}\n"
        f"**Site:** `{site_disp}`\n"
        f"**API Key:** `{api_disp}`\n"
        f"**Verify Duration:** `{time_hr} Hours`\n\n"
        f"What would you like to do?"
    )

    buttons = [
        [InlineKeyboardButton("✏️ Edit URL/API", callback_data=f"short_edit_{chat_id}_{slot}"),
         InlineKeyboardButton("⏳ Edit Time", callback_data=f"short_time_{chat_id}_{slot}")],
        [InlineKeyboardButton("🗑 Disable Slot", callback_data=f"short_disable_{chat_id}_{slot}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"short_main_{chat_id}")]
    ]
    return text, InlineKeyboardMarkup(buttons)

# ==========================================
# 1️⃣ COMMAND HANDLER: /settings
# ==========================================
@Client.on_message(filters.command("settings") & (filters.group | filters.private))
async def settings_command(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_admin(client, chat_id, user_id):
        return await message.reply("❌ You must be an admin to use this command.")

    text, markup = await get_main_settings_ui(chat_id)
    await message.reply(text, reply_markup=markup)

# ==========================================
# 2️⃣ CALLBACK QUERY HANDLERS
# ==========================================
@Client.on_callback_query(filters.regex(r"^short_"))
async def shortener_callbacks(client: Client, callback: CallbackQuery):
    data = callback.data.split("_")
    action = data[1] # main, menu, edit, disable, close, mode, time, cancel
    user_id = callback.from_user.id

    if action == "close":
        return await callback.message.delete()

    chat_id = int(data[2])
    
    # Permission Check inside callback
    if not await is_admin(client, chat_id, user_id):
        return await callback.answer("❌ You are not allowed to do this.", show_alert=True)

    # Action: Main Menu
    if action == "main":
        text, markup = await get_main_settings_ui(chat_id)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Toggle Mode
    elif action == "mode":
        settings = await db_users.get_group_shortener_settings(chat_id)
        new_mode = "together" if settings.get("mode") == "smart" else "smart"
        await db_users.update_shortener_mode(chat_id, new_mode)
        text, markup = await get_main_settings_ui(chat_id)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Slot Menu
    elif action == "menu":
        slot = int(data[3])
        text, markup = await get_slot_ui(chat_id, slot)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Disable Slot
    elif action == "disable":
        slot = int(data[3])
        await db_users.update_shortener_slot(chat_id, slot, "", "") # Clear in DB
        await callback.answer(f"✅ Slot {slot} Disabled successfully!", show_alert=True)
        text, markup = await get_slot_ui(chat_id, slot)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Edit Slot API (Starts Input State)
    elif action == "edit":
        slot = int(data[3])
        AWAITING_INPUT[user_id] = {"chat_id": chat_id, "slot": slot, "type": "api"}
        
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Process", callback_data=f"short_cancel_{chat_id}")]])
        
        await callback.message.edit_text(
            f"✏️ **Editing Slot {slot} (URL & API)**\n\n"
            f"Please send the **Website URL** and **API Key** separated by a space.\n\n"
            f"👉 **Example:** `api.shareus.io 1234567890abcdef`\n\n"
            f"*(Waiting for your reply...)*",
            reply_markup=cancel_markup
        )

    # Action: Edit Slot Time
    elif action == "time":
        slot = int(data[3])
        AWAITING_INPUT[user_id] = {"chat_id": chat_id, "slot": slot, "type": "time"}
        
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Process", callback_data=f"short_cancel_{chat_id}")]])
        
        await callback.message.edit_text(
            f"⏳ **Editing Time for Slot {slot}**\n\n"
            f"Please send the verification duration in **Hours**.\n\n"
            f"👉 **Example:** `24` or `12`\n\n"
            f"*(Waiting for your reply...)*",
            reply_markup=cancel_markup
        )

    # Action: Cancel Edit
    elif action == "cancel":
        if user_id in AWAITING_INPUT:
            del AWAITING_INPUT[user_id]
        text, markup = await get_main_settings_ui(chat_id)
        await callback.message.edit_text(text, reply_markup=markup)


# ==========================================
# 3️⃣ INPUT RECEIVER (Message Handler)
# ==========================================
@Client.on_message(filters.text & filters.private, group=1)
async def input_receiver(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check if we are waiting for input from this user
    if user_id not in AWAITING_INPUT:
        return # Skip if not in state

    state_data = AWAITING_INPUT[user_id]
    chat_id = state_data["chat_id"]
    slot = state_data["slot"]
    input_type = state_data["type"]

    # --- Handle API Input ---
    if input_type == "api":
        input_text = message.text.strip().split()
        if len(input_text) != 2:
            return await message.reply("⚠️ **Invalid Format!**\n\nPlease send both Site and API separated by a space.\nExample: `shareus.io my_api_key`\n\nOr click Cancel above.")

        site = input_text[0]
        api = input_text[1]

        await db_users.update_shortener_slot(chat_id, slot, site, api)
        del AWAITING_INPUT[user_id]

        success_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"short_main_{chat_id}")]])
        await message.reply(
            f"✅ **Shortener Slot {slot} Updated!**\n\n"
            f"🌐 **Site:** `{site}`\n"
            f"🔑 **API:** `{api[:5]}...`",
            reply_markup=success_markup
        )

    # --- Handle Time Input ---
    elif input_type == "time":
        try:
            hours = int(message.text.strip())
            if hours <= 0: raise ValueError
            
            seconds = hours * 3600
            await db_users.update_shortener_time(chat_id, slot, seconds)
            del AWAITING_INPUT[user_id]

            success_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"short_main_{chat_id}")]])
            await message.reply(
                f"✅ **Time for Slot {slot} Updated!**\n\n"
                f"⏳ **New Duration:** `{hours} Hours`",
                reply_markup=success_markup
            )
        except ValueError:
            return await message.reply("⚠️ **Invalid Format!**\n\nPlease send a valid number of hours (e.g., `12` or `24`).\n\nOr click Cancel above.")
