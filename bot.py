from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN
from flask import Flask
import threading
import os

# ==========================================
# PART 1: WEBSERVER (Render Error Hatane ke liye)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Bot is running!'

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Server ko background thread me chalana
t = threading.Thread(target=run_web_server)
t.daemon = True
t.start()

# ==========================================
# PART 2: MAIN BOT CODE
# ==========================================

# Client initialize
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- START COMMAND ---
@app.on_message(filters.command("start"))
async def start_command(client, message):
    # Bot ka username nikalein
    bot_info = await client.get_me()
    username = bot_info.username
    
    # 100% Working Image URL (Wikimedia Python Logo)
    # Yeh link reliable hai aur error nahi dega
    IMG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/480px-Python-logo-notext.svg.png"

    # Buttons Setup
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

    # Photo aur Caption bhejna
    await message.reply_photo(
        photo=IMG_URL,
        caption=(
            "**Namaste!** 🙏\n\n"
            "Main ek advanced Telegram Bot hu.\n"
            "Mujhe apne group mein add karne ke liye niche button dabayein."
        ),
        reply_markup=buttons
    )

# --- ABOUT BUTTON HANDLER ---
@app.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback_query):
    info_text = (
        "🤖 **About This Bot**\n"
        "------------------\n"
        "🔹 **Language:** Python (Pyrogram)\n"
        "🔹 **Function:** Group Management\n"
        "🔹 **Developer:** You"
    )
    
    await callback_query.answer("Details loaded!")
    await callback_query.message.reply_text(info_text)

# --- HII MESSAGE HANDLER ---
@app.on_message(filters.text & filters.regex(r"(?i)^hii$"))
async def respond_to_hii(client, message):
    await message.reply_text("Hello ji! Kaise ho? 😃")

# --- RUN ---
print("Bot Started... Ab koi error nahi aayega.")
app.run()
