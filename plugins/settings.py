import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

# ==========================================
# 🗄️ DUMMY ASYNC DATABASE PLACEHOLDER
# ==========================================
# Aap isko apne MongoDB functions se replace kar lena
class DummyDB:
    def __init__(self):
        self.data = {} # In-memory storage for testing

    async def get_shortener(self, chat_id, slot):
        # Returns dict like {"site": "example.com", "api": "12345"} or None
        chat_data = self.data.get(str(chat_id), {})
        return chat_data.get(f"slot_{slot}", {"site": None, "api": None})

    async def update_shortener(self, chat_id, slot, site, api):
        chat_id_str = str(chat_id)
        if chat_id_str not in self.data:
            self.data[chat_id_str] = {}
        self.data[chat_id_str][f"slot_{slot}"] = {"site": site, "api": api}

db = DummyDB()

# ==========================================
# 🧠 STATE TRACKER FOR INPUT
# ==========================================
# Ye track karega ki kaunsa user kis group ke kis slot ke liye input de raha hai
AWAITING_INPUT = {}  # Format: {user_id: {"chat_id": chat_id, "slot": slot}}

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
    """Main Menu showing all 3 slots"""
    buttons = [
        [InlineKeyboardButton("⚙️ Shortener Slot 1", callback_data=f"short_menu_{chat_id}_1")],
        [InlineKeyboardButton("⚙️ Shortener Slot 2", callback_data=f"short_menu_{chat_id}_2")],
        [InlineKeyboardButton("⚙️ Shortener Slot 3", callback_data=f"short_menu_{chat_id}_3")],
        [InlineKeyboardButton("❌ Close", callback_data="short_close")]
    ]
    text = "⚙️ **Shortener Configuration Settings**\n\nSelect a slot below to View, Edit or Disable the URL shortener for this chat."
    return text, InlineKeyboardMarkup(buttons)

async def get_slot_ui(chat_id, slot):
    """Sub-menu showing details of a specific slot"""
    data = await db.get_shortener(chat_id, slot)
    site = data.get("site")
    api = data.get("api")

    status = "🟢 Active" if site and api else "🔴 Disabled"
    site_disp = site if site else "None"
    api_disp = api[:5] + "..." if api else "None"

    text = (
        f"🔗 **Shortener Settings (Slot {slot})**\n\n"
        f"**Status:** {status}\n"
        f"**Site:** `{site_disp}`\n"
        f"**API Key:** `{api_disp}`\n\n"
        f"What would you like to do?"
    )

    buttons = [
        [InlineKeyboardButton("✏️ Edit", callback_data=f"short_edit_{chat_id}_{slot}"),
         InlineKeyboardButton("🗑 Disable", callback_data=f"short_disable_{chat_id}_{slot}")],
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
    action = data[1] # main, menu, edit, disable, close
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

    # Action: Slot Menu
    elif action == "menu":
        slot = int(data[3])
        text, markup = await get_slot_ui(chat_id, slot)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Disable Slot
    elif action == "disable":
        slot = int(data[3])
        await db.update_shortener(chat_id, slot, None, None) # Passing None clears it
        await callback.answer(f"✅ Slot {slot} Disabled successfully!", show_alert=True)
        text, markup = await get_slot_ui(chat_id, slot)
        await callback.message.edit_text(text, reply_markup=markup)

    # Action: Edit Slot (Starts Input State)
    elif action == "edit":
        slot = int(data[3])
        # Set the state for this user
        AWAITING_INPUT[user_id] = {"chat_id": chat_id, "slot": slot}
        
        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Process", callback_data=f"short_cancel_{chat_id}")]])
        
        await callback.message.edit_text(
            f"✏️ **Editing Slot {slot}**\n\n"
            f"Please send the **Website URL** and **API Key** separated by a space.\n\n"
            f"👉 **Example:** `api.shareus.io 1234567890abcdef`\n\n"
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

    input_text = message.text.strip().split()

    if len(input_text) != 2:
        return await message.reply("⚠️ **Invalid Format!**\n\nPlease send both Site and API separated by a space.\nExample: `shareus.io my_api_key`\n\nOr click Cancel above.")

    site = input_text[0]
    api = input_text[1]

    # Save to Database
    await db.update_shortener(chat_id, slot, site, api)
    
    # Clear the state
    del AWAITING_INPUT[user_id]

    # Send Success message with back button
    success_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"short_main_{chat_id}")]])
    await message.reply(
        f"✅ **Shortener Slot {slot} Updated!**\n\n"
        f"🌐 **Site:** `{site}`\n"
        f"🔑 **API:** `{api[:5]}...`",
        reply_markup=success_markup
    )
