# bot.py
from pyrogram import Client, filters
import random
from config import API_ID, API_HASH, BOT_TOKEN
from flask import Flask
import threading
import os

# --- FLASK SERVER START (Render ko khush karne ke liye) ---
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Bot is running!'

def run_web():
    # Render PORT env variable deta hai, nahi to 8080 use karega
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Flask ko alag thread me chalana
t = threading.Thread(target=run_web)
t.daemon = True
t.start()
# --- FLASK SERVER END ---


# --- MAIN BOT CODE ---
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

REPLY_LIST = [
    "hello",
    "hello cutie",
    "Hello Mr",
    "hello guys",
    "kaise ho dear"
]

@app.on_message(filters.text & filters.regex(r"(?i)^hii$"))
async def respond_to_hii(client, message):
    selected_reply = random.choice(REPLY_LIST)
    await message.reply_text(selected_reply)
    print(f"Replied: {selected_reply}")

print("Bot start ho gaya hai...")
app.run()
