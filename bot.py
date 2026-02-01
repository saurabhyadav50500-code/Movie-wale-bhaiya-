import logging
import logging.config
import os
import threading
import asyncio
from flask import Flask
from pyrogram import Client, idle
from info import API_ID, API_HASH, BOT_TOKEN

# Database Imports
from database.ia_filterdb import db
from database.analytics import analytics

# 1. Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# 2. Webserver
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
    print("-----------------------------------------", flush=True)
    print("🚀 Bot Start Ho Raha Hai...", flush=True)
    
    # Webserver start
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    
    try:
        await app.start()
        print("✅ Telegram Se Connect Ho Gaya!", flush=True)
    except Exception as e:
        print(f"❌ Connection Error: {e}", flush=True)
        return

    # --- DATABASE CONNECTION (With Timeout Fix) ---
    print("⏳ Database Connecting...", flush=True)
    try:
        # Timeout lagaya hai taki bot atke nahi
        await asyncio.wait_for(db.ensure_indexes(), timeout=10.0)
        print("✅ Main Database Ready!", flush=True)
        
        try:
            await asyncio.wait_for(analytics.ensure_indexes(), timeout=5.0)
            print("✅ Analytics Database Ready!", flush=True)
        except asyncio.TimeoutError:
            print("⚠️ Analytics Slow tha, Skip kar diya (Bot chalega!)", flush=True)
        except Exception as e:
            print(f"⚠️ Analytics Error: {e}", flush=True)
            
    except Exception as e:
        print(f"❌ Main Database Error: {e}", flush=True)

    # --- CONFIRMATION ---
    me = await app.get_me()
    print(f"🤖 Bot Started as: @{me.username}", flush=True)
    print("➡️ Ab Telegram par /start bhejo!", flush=True)
    print("-----------------------------------------", flush=True)
    
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(start_bot())
