from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import API_ID, API_HASH, BOT_TOKEN
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

app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins") # ✅ Ye line bahut zaroori hai!
)

# --- START COMMAND ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # 👇 YAHAN CHANGE KIYA HAI (CRITICAL FIX)
    # Agar message me "/start" ke baad kuch aur bhi hai (jaise file_id), 
    # to ye function yahin ruk jayega aur Plugin ko kaam karne dega.
    if len(message.command) > 1:
        return 

    # Bot ka username nikalein
    bot_info = await client.get_me()
    username = bot_info.username
    
    IMG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/480px-Python-logo-notext.svg.png"

    # Buttons Setup
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="➕ Add me to group",
                url=f"http://t.me/{username}?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ About",
                callback_data="about_section"
            )
        ]
    ])

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
        "🔹 **Function:** Auto Filter & File Store\n"
        "🔹 **Developer:** You"
    )
    
    await callback_query.answer("Details loaded!")
    await callback_query.message.reply_text(info_text)

# --- HII MESSAGE HANDLER ---
@app.on_message(filters.text & filters.regex(r"(?i)^hii$"))
async def respond_to_hii(client, message):
    await message.reply_text("Hello ji! Kaise ho? 😃")

# --- RUN ---
print("Bot Started... Ab Plugins bhi load honge! 🟢")
app.run()
