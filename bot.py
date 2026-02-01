import logging
import logging.config
import os
import threading
import asyncio
from flask import Flask
from pyrogram import Client, idle, filters  # 'filters' add kiya hai test ke liye
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

# 🚨 EMERGENCY TEST HANDLER 🚨
# Ye bina plugins folder ke chalega. Agar ye chala, to bot 100% sahi hai, bas folder mein galti hai.
@app.on_message(filters.command("check"))
async def check_handler(client, message):
    await message.reply_text("✅ **Bot Zinda Hai!**\nProblem 'plugins' folder ya files mein hai, bot mein nahi.")

async def start_bot():
    print("-----------------------------------------", flush=True)
    print("🚀 Bot Start Ho Raha Hai...", flush=True)
    
    # Debugging: Check Plugins Folder
    if os.path.exists("plugins"):
        files = os.listdir("plugins")
        print(f"📂 Plugins Folder Files: {files}", flush=True)
        if "commands.py" not in files:
            print("❌ DANGER: 'commands.py' plugins folder mein nahi hai!", flush=True)
    else:
        print("❌ CRITICAL: 'plugins' folder hi gayab hai!", flush=True)

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

    # --- DATABASE CONNECTION ---
    print("⏳ Database Connecting...", flush=True)
    try:
        await asyncio.wait_for(db.ensure_indexes(), timeout=10.0)
        print("✅ Main Database Ready!", flush=True)
        
        try:
            await asyncio.wait_for(analytics.ensure_indexes(), timeout=5.0)
            print("✅ Analytics Database Ready!", flush=True)
        except:
            print("⚠️ Analytics Skipped", flush=True)
            
    except Exception as e:
        print(f"❌ Main Database Error: {e}", flush=True)

    me = await app.get_me()
    print(f"🤖 Bot Started as: @{me.username}", flush=True)
    print("➡️ Telegram par '/check' bhejo!", flush=True)
    print("-----------------------------------------", flush=True)
    
    await idle()
    await app.stop()

if __name__ == "__main__":
    app.run(start_bot())
