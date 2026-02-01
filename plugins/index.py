import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

INDEX_SESSION = {}

# STEP 1
@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def start_index_step1(bot: Client, message: Message):
    user_id = message.from_user.id
    INDEX_SESSION[user_id] = {'step': 'waiting_forward'}
    await message.reply_text("🆔 **Indexing Step 1:**\nApne Channel se **Last Message** forward karein.")

# STEP 2
@Client.on_message(filters.forwarded & filters.user(ADMINS))
async def handle_forward_step2(bot: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in INDEX_SESSION or INDEX_SESSION[user_id]['step'] != 'waiting_forward': return
    if not message.forward_from_chat: return await message.reply("❌ Channel se forward karein.")

    INDEX_SESSION[user_id].update({
        'step': 'waiting_skip',
        'channel_id': message.forward_from_chat.id,
        'last_msg_id': message.forward_from_message_id
    })
    await message.reply_text(f"✅ **Channel Detected:** {message.forward_from_chat.title}\n**Step 2:** Skip number likhein (Ex: 0).")

# STEP 3 (Isme Restart Check hai)
@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["index", "start"]))
async def handle_skip_step3(bot: Client, message: Message):
    user_id = message.from_user.id
    
    # 🔴 AGAR BOT RESTART HUA HAI TO BATAO
    if user_id not in INDEX_SESSION:
        if message.text.isdigit():
            await message.reply("⚠️ **Alert: Bot Restart Ho Gaya Tha!**\nSession expire ho gaya. Kripya `/index` dubara shuru karein.")
        return

    if INDEX_SESSION[user_id]['step'] != 'waiting_skip': return

    try: skip_num = int(message.text)
    except: return await message.reply("❌ Number likhein.")

    INDEX_SESSION[user_id]['skip'] = skip_num
    INDEX_SESSION[user_id]['step'] = 'waiting_confirm'

    await message.reply_text(
        f"📊 **Summary:** Skip {skip_num} messages.\nStart?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Start", callback_data="idx_start"), InlineKeyboardButton("❌ Cancel", callback_data="idx_cancel")]])
    )

# STEP 4 (Processing)
@Client.on_callback_query(filters.regex(r"^idx_"))
async def index_process_handler(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if query.data == "idx_cancel":
        if user_id in INDEX_SESSION: del INDEX_SESSION[user_id]
        return await query.message.edit("❌ Cancelled.")

    if user_id not in INDEX_SESSION: return await query.answer("⚠️ Session Expired.", show_alert=True)

    session = INDEX_SESSION[user_id]
    del INDEX_SESSION[user_id]
    
    msg = await query.message.edit("⏳ **Initializing...**")
    chat_id, last_id, current = session['channel_id'], session['last_msg_id'], session['skip'] + 1
    total, saved, dupes = 0, 0, 0
    
    try:
        while current <= last_id:
            end = min(current + 199, last_id)
            ids = list(range(current, end + 1))
            try:
                messages = await bot.get_messages(chat_id, ids)
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
                messages = await bot.get_messages(chat_id, ids)
            except: current += 200; continue

            for m in messages:
                total += 1
                if m and (m.document or m.video or m.audio):
                    try:
                        if await db.save_file(m): saved += 1
                        else: dupes += 1
                    except: pass
            
            try: await msg.edit(f"🔄 **Indexing...**\nScanned: {total}\nSaved: {saved}")
            except: pass
            current += 200

        await msg.edit(f"✅ **Done!**\nSaved: {saved}\nDupes: {dupes}")
    except Exception as e: await msg.edit(f"❌ Error: {e}")
