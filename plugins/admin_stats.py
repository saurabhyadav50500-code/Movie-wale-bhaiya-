from pyrogram import Client, filters
from database.analytics import analytics
from info import ADMINS

@Client.on_message(filters.command("topsearch") & filters.user(ADMINS))
async def top_search_stats(bot, message):
    msg = await message.reply("⏳ Fetching Data...")
    data = await analytics.get_top_searches(limit=20)
    
    if not data: return await msg.edit("No data yet.")
    
    text = "🔥 **All Time Top Searches**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id'].title()}` ({item['hits']})\n"
    await msg.edit(text)

@Client.on_message(filters.command("missing") & filters.user(ADMINS))
async def missing_content_stats(bot, message):
    msg = await message.reply("⏳ Calculating...")
    data = await analytics.get_failed_searches(limit=20)
    
    if not data: return await msg.edit("No failed searches! 😎")
    
    text = "❌ **Most Missing Movies (Failed Searches)**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id']}` ({item['misses']} times)\n"
    await msg.edit(text)

@Client.on_message(filters.command("trend") & filters.user(ADMINS))
async def trending_stats(bot, message):
    msg = await message.reply("⏳ Checking trends...")
    data = await analytics.get_trending_searches(hours=24, limit=20)
    
    if not data: return await msg.edit("No trends in last 24h.")
    
    text = "📈 **Trending (Last 24 Hours)**\n\n"
    for i, item in enumerate(data, 1):
        text += f"{i}. `{item['_id'].title()}` ({item['hits']})\n"
    await msg.edit(text)
