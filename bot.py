from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN
from flask import Flask
import threading
import os

# ==========================================
# PART 1: DUMMY FLASK SERVER (Render ke liye)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Hello! Bot is running perfectly.'

def run_web_server():
    # Render se PORT lo, agar nahi mila to 8080 use karo
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Server ko alag thread me start karo taaki bot na ruke
t = threading.Thread(target=run_web_server)
t.daemon = True
t.start()

# ==========================================
# PART 2: MAIN TELEGRAM BOT LOGIC
# ==========================================

# Client initialize karein
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- START COMMAND WITH BUTTONS ---
@app.on_message(filters.command("start"))
async def start_command(client, message):
    # Bot username fetch karo
    bot_info = await client.get_me()
    username = bot_info.username
    
    # Photo URL
    IMG_URL = "https://graph.org/file/5d8a6e843c0818276f625.jpg"

    # Buttons
    buttons = InlineKeyboardMarkup([
        [
            # Button 1: Add to Group
            InlineKeyboardButton(
                text="➕ Add me to group",
                url=f"http://t.me/{username}?startgroup=true"
            )
        ],
        [
            # Button 2: About
            InlineKeyboardButton(
                text="ℹ️ About",
                callback_data="about_section"
            )
        ]
    ])

    await message.reply_photo(
        photo=IMG_URL,
        caption="**Hello Dear!** 👋\n\nMain online hu. Mujhe group me add karne ke liye button dabayein.",
        reply_markup=buttons
    )

# --- ABOUT BUTTON HANDLER ---
@app.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback_query):
    about_text = (
        "🤖 **Bot Information**\n"
        "-----------------------\n"
        "🔹 **Name:** Group Manager Bot\n"
        "🔹 **Language:** Python (Pyrogram)\n"
        "🔹 **Server:** Render\n"
        "🔹 **Developer:** You"
    )
    await callback_query.answer("Fetching details...")
    await callback_query.message.reply_text(about_text)

# --- HII MESSAGE HANDLER ---
@app.on_message(filters.text & filters.regex(r"(?i)^hii$"))
async def respond_to_hii(client, message):
    await message.reply_text("Hello cutie! Kaise ho? 😉")

# --- BOT START ---
print("Bot aur Web Server dono start ho gaye hain...")
app.run()
