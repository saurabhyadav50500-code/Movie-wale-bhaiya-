from pyrogram import Client, filters
from pyrogram.types import Message

# 👇 Database Imports
from database.analytics import analytics
from database.ia_filterdb import db
from database.users_chats_db import db_users
from info import ADMINS

# ==========================================
# 📊 GENERAL STATS (Render Friendly)
# ==========================================
@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def get_general_stats(bot, message):
    """
    Shows total indexed files, total users, and groups.
    (Disk usage removed for Render)
    """
    msg = await message.reply("⏳ **Fetching Database Stats...**")
    
    # 1. Total Files Count
    total_files = await db.col.count_documents({})
    
    # 2. Total Users & Groups Count
    total_users = await db_users.col.count_documents({"id": {"$gt": 0}})
    total_groups = await db_users.col.count_documents({"id": {"$lt": 0}})

    text = (
        f"📊 **BOT STATISTICS**\n\n"
        f"📂 **Total Files:** `{total_files}`\n"
        f"👤 **Total Users:** `{total_users}`\n"
        f"👥 **Total Groups:** `{total_groups}`\n\n"
        f"☁️ **Hosted on:** Render (PaaS)"
    )
    
    await msg.edit(text)

# ==========================================
# 🔥 TOP SEARCHES
# ==========================================
@Client.on_message(filters.command("topsearch") & filters.user(ADMINS))
async def top_search_stats(bot, message):
    msg = await message.reply("⏳ Fetching Data...")
    data = await analytics.get_top_searches(limit=20)
    
    if not data: return await msg.edit("❌ Abhi tak koi search data nahi hai.")
    
    text = "🔥 **All Time Top Searches**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id'].title()}` ({item['hits']} hits)\n"
    await msg.edit(text)

# ==========================================
# ❌ MISSING CONTENT (Failed Searches)
# ==========================================
@Client.on_message(filters.command("missing") & filters.user(ADMINS))
async def missing_content_stats(bot, message):
    msg = await message.reply("⏳ Calculating...")
    data = await analytics.get_failed_searches(limit=20)
    
    if not data: return await msg.edit("✅ Koi missing content nahi hai! Sab badhiya hai.")
    
    text = "❌ **Most Missing Movies**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id']}` ({item['misses']} times failed)\n"
    
    text += "\n💡 _In movies ko jaldi upload karke /index karein._"
    await msg.edit(text)

# ==========================================
# 📈 TRENDING (Last 24 Hours)
# ==========================================
@Client.on_message(filters.command("trend") & filters.user(ADMINS))
async def trending_stats(bot, message):
    msg = await message.reply("⏳ Checking trends...")
    data = await analytics.get_trending_searches(hours=24, limit=20)
    
    if not data: return await msg.edit("💤 Pichle 24 ghante mein koi khaas trend nahi hai.")
    
    text = "📈 **Trending Searches (Last 24 Hours)**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id'].title()}` ({item['hits']} hits)\n"
    await msg.edit(text)
