import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

INDEX_SESSION = {}

# ==========================================
# STEP 1: INITIAL COMMAND (Priority Group 1)
# ==========================================
@Client.on_message(filters.command("index") & filters.user(ADMINS), group=1)
async def start_index_step1(bot: Client, message: Message):
    user_id = message.from_user.id
    INDEX_SESSION[user_id] = {'step': 'waiting_forward'}
    await message.reply_text("🆔 **Indexing Step 1:**\nApne Channel se **Last Message** forward karein.")

# ==========================================
# STEP 2: HANDLE FORWARD
# ==========================================
@Client.on_message(filters.forwarded & filters.user(ADMINS), group=1)
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

# ==========================================
# STEP 3: HANDLE SKIP NUMBER (Restart Check Ke Sath)
# ==========================================
@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["index", "start"]), group=1)
async def handle_skip_step3(bot: Client, message: Message):
    user_id = message.from_user.id
    
    # 🔴 Restart Check (Agar Bot restart hua to ye chalega)
    if user_id not in INDEX_SESSION:
        if message.text.isdigit():
            await message.reply("⚠️ **Bot Restart Ho Gaya Tha!**\nSession expire ho gaya. `/index` dubara karein.")
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

# ==========================================
# STEP 4: SMART INDEXING PROCESSING
# ==========================================
@Client.on_callback_query(filters.regex(r"^idx_"), group=1)
async def index_process_handler(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if query.data == "idx_cancel":
        if user_id in INDEX_SESSION: del INDEX_SESSION[user_id]
        return await query.message.edit("❌ Cancelled.")

    if user_id not in INDEX_SESSION: return await query.answer("⚠️ Session Expired.", show_alert=True)

    session = INDEX_SESSION[user_id]
    del INDEX_SESSION[user_id]
    
    msg = await query.message.edit("⏳ **Initializing...**")
    
    # --- COUNTERS ---
    total_scanned = 0
    saved = 0
    duplicates = 0
    others_skipped = 0
    
    current = session['skip'] + 1
    last_id = session['last_msg_id']
    chat_id = session['channel_id']
    
    try:
        while current <= last_id:
            end = min(current + 199, last_id)
            ids = list(range(current, end + 1))
            
            try:
                # 🚀 Messages Fetching (FloodWait Safe)
                messages = await bot.get_messages(chat_id, ids)
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
                messages = await bot.get_messages(chat_id, ids)
            except Exception:
                # Agar messages fetch hi na ho paye (Deleted block)
                others_skipped += len(ids)
                current += 200
                continue

            for m in messages:
                total_scanned += 1
                
                # Check 1: Empty or Deleted Message
                if not m or m.empty:
                    others_skipped += 1
                    continue
                
                # Check 2: Valid Media (Video/Doc/Audio)
                if m.document or m.video or m.audio:
                    # DB Call: Returns 'saved', 'duplicate', or 'error'
                    status = await db.save_file(m)
                    
                    if status == 'saved':
                        saved += 1
                    elif status == 'duplicate':
                        duplicates += 1
                    else:
                        others_skipped += 1 # Save fail hua to skip me daalo
                else:
                    # Check 3: Text / Stickers / Photos
                    others_skipped += 1

            # Update Status (Har 200 messages par)
            try:
                await msg.edit(
                    f"🔄 **Indexing in Progress...**\n\n"
                    f"👀 Scanned: `{total_scanned}` / `{last_id}`\n"
                    f"💾 Saved: `{saved}`\n"
                    f"♻️ Duplicates: `{duplicates}`\n"
                    f"🗑 Skipped (Others): `{others_skipped}`"
                )
            except: pass
            
            current += 200

        # --- FINAL SUMMARY REPORT ---
        await msg.edit(
            f"✅ **Indexing Completed!**\n\n"
            f"📊 **Total Scanned:** `{total_scanned}`\n"
            f"💾 **Saved:** `{saved}`\n"
            f"♻️ **Duplicates:** `{duplicates}`\n"
            f"🗑 **Others (Skipped):** `{others_skipped}`"
        )

    except Exception as e:
        await msg.edit(f"❌ Error: {e}")
