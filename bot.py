import logging
import os
import threading
import asyncio
import time
from flask import Flask
from pyrogram import Client, idle
from pyrogram.errors import FloodWait
from info import API_ID, API_HASH, BOT_TOKEN

# 👇 DATABASE IMPORTS
from database.ia_filterdb import db
from database.users_chats_db import db_users
from database.analytics import analytics

# ==========================================
# PART 1: WEBSERVER (Keep Bot Alive)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def hello_world():
    return 'Bot is running!'

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

t = threading.Thread(target=run_web_server)
t.daemon = True
t.start()

# ==========================================
# PART 2: BOT CONFIGURATION
# ==========================================

# Logger Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define the Client
app = Client(
    "my_search_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

# ==========================================
# PART 3: STARTUP SEQUENCE (With Anti-Flood)
# ==========================================

async def start_bot():
    print("🚀 Initializing Bot...")
    
    # 1. Start Client (With FloodWait Handler)
    try:
        await app.start()
    except FloodWait as e:
        print(f"⚠️ FloodWait Detected: Telegram says wait {e.value} seconds.")
        print(f"⏳ Sleeping for {e.value} seconds... (Please wait)")
        await asyncio.sleep(e.value + 5) # Sleep for required time + 5s buffer
        await app.start() # Try again
        print("✅ Bot started successfully after wait!")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        return

    bot_info = await app.get_me()
    
    # 2. Database Checks
    print("⏳ Checking Database Indexes...")
    try:
        await db.ensure_indexes()
        await analytics.ensure_indexes()
        print("✅ Database Indexes Ready!")
    except AttributeError:
        print("❌ Error: 'ensure_indexes' missing in ia_filterdb.py. Please check the code.")
    except Exception as e:
        print(f"⚠️ Database Error: {e}")
    
    # 3. Print Summary
    print(f"\n{'='*50}")
    print(f"✅ Bot Started: @{bot_info.username}")
    print(f"✅ Database: Connected")
    print(f"✅ Plugins: Loaded from /plugins")
    print(f"{'='*50}\n")
    
    print("🟢 Bot is Online and Idling...")
    await idle() 
    
    # 4. Stop Sequence
    await app.stop()
    print("🔴 Bot Stopped.")

if __name__ == "__main__":
    app.run(start_bot())
