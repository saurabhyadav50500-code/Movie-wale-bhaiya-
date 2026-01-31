import logging
import logging.config
import os
import threading
from flask import Flask

# Pyrogram Imports
from pyrogram import Client, idle

# Config Imports
from info import API_ID, API_HASH, BOT_TOKEN

# Database Imports 
# (Ye tabhi chalega jab database/__init__.py bana loge!)
from database.ia_filterdb import db
from database.analytics import analytics

# 1. Logger Setup (Sirf Errors aur Bot Status dikhega)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler()]
)

# Pyrogram ke faaltu logs ko chup karana (WARNING level only)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 2. Webserver (Render ke liye)
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Bot Live Hai!'

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# 3. Bot Client
app = Client(
    "my_search_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins") 
)

async def start_bot():
    print("-----------------------------------------")
    print("🚀 Bot Start Ho Raha Hai...")
    
    # Webserver start
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    
    # Bot Start
    try:
        await app.start()
        print("✅ Telegram Se Connect Ho Gaya!")
    except Exception as e:
        print(f"❌ Telegram Connection Error: {e}")
        return

    # Database Check
    print("⏳ Database Check Kar Raha Hoon...")
    try:
        await db.ensure_indexes()
        await analytics.ensure_indexes()
        print("✅ Database Connected Successfully!")
    except Exception as e:
        print(f"⚠️ Database Error: {e}")
        print("❌ 'database/__init__.py' abhi bhi missing hai shayad!")

    me = await app.get_me()
    print(f"🤖 Bot Start Ho Gaya: @{me.username}")
    print("➡️ Ab Telegram par /start bhejo")
    print("-----------------------------------------")
    
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(start_bot())
