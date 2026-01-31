import logging
import logging.config
import os
import threading
from flask import Flask

# Pyrogram Imports
from pyrogram import Client, idle
from pyrogram import errors

# Config Imports
from info import API_ID, API_HASH, BOT_TOKEN

# Database Imports (Ye tabhi chalega jab database/__init__.py maujood ho)
from database.ia_filterdb import db
from database.analytics import analytics

# 1. Logger Setup (Errors dekhne ke liye)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 2. Webserver (Render/Koyeb ke liye)
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Mera Bot Start Ho Gaya Hai!'

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# 3. Bot Client Definition
app = Client(
    "my_search_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")  # 👈 Ye folder sahi hona chahiye
)

async def start_bot():
    print("-----------------------------------------")
    print("🚀 System Booting...")
    
    # Webserver start
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    
    # Bot Start
    try:
        await app.start()
        print("✅ Bot Client Connected!")
    except Exception as e:
        print(f"❌ Bot Token/API Error: {e}")
        return

    # Database Check
    print("⏳ Checking Database Connection...")
    try:
        await db.ensure_indexes()
        await analytics.ensure_indexes()
        print("✅ Database Connected & Indexes Ready!")
    except Exception as e:
        print(f"⚠️ Database Error: {e}")
        print("❌ Shayad 'database/__init__.py' file missing hai ya MongoDB URL galat hai.")

    # Bot Info Print
    me = await app.get_me()
    print(f"🤖 Bot Started as: @{me.username}")
    print("-----------------------------------------")
    
    await idle()  # Bot ko yahan roke rakho
    
    await app.stop()
    print("🔴 Bot Stopped.")

if __name__ == "__main__":
    app.run(start_bot())
