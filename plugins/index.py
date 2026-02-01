import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

# Session Storage
INDEX_SESSION = {}

# ==========================================
# STEP 1: INITIAL COMMAND
# ==========================================
@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def start_index_step1(bot: Client, message: Message):
    """Step 1: Admin se last message maangta hai."""
    user_id = message.from_user.id
    # Session start karein
    INDEX_SESSION[user_id] = {'step': 'waiting_forward'}
    
    print(f"DEBUG: Index process started for {user_id}") # Debug Log
    
    await message.reply_text(
        "🆔 **Indexing Step 1:**\n\n"
        "Apne Channel se **Last Message** (Latest Upload) forward karein.\n"
        "⚠️ **Note:** Main us channel mein Admin hona chahiye."
    )

# ==========================================
# STEP 2: HANDLE FORWARD
# ==========================================
@Client.on_message(filters.forwarded & filters.user(ADMINS))
async def handle_forward_step2(bot: Client, message: Message):
    """Step 2: Channel ID capture karta hai."""
    user_id = message.from_user.id
    
    # Check karein ki user ka session active hai ya nahi
    if user_id not in INDEX_SESSION:
        # Agar session nahi hai, to ignore karein (shayad purana forward ho)
        return

    if INDEX_SESSION[user_id]['step'] != 'waiting_forward':
        return

    if not message.forward_from_chat:
        return await message.reply("❌ Ye Message Channel se forwarded nahi lag raha.")

    target_chat_id = message.forward_from_chat.id
    last_msg_id = message.forward_from_message_id

    # Session Update
    INDEX_SESSION[user_id].update({
        'step': 'waiting_skip',
        'channel_id': target_chat_id,
        'last_msg_id': last_msg_id
    })
    
    print(f"DEBUG: Channel Detected: {target_chat_id} Last ID: {last_msg_id}") # Debug Log

    await message.reply_text(
        f"✅ **Detected Channel:** `{message.forward_from_chat.title}`\n"
        f"🔢 **Last ID:** `{last_msg_id}`\n\n"
        "**Step 2:** Kitne messages skip karne hain? (Shuru se karne ke liye `0` likhein)."
    )

# ==========================================
# STEP 3: HANDLE SKIP NUMBER (Fix Yahan Hai)
# ==========================================
@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["index", "start", "broadcast"]))
async def handle_skip_step3(bot: Client, message: Message):
    """Step 3: Skip number leta hai."""
    user_id = message.from_user.id
    text = message.text

    # --- 🛑 SAFETY CHECK (Agar Bot Restart Hua Ho) ---
    if user_id not in INDEX_SESSION:
        # Agar koi number bheje lekin session na ho, to batao ki restart hua hai
        if text.isdigit():
            await message.reply(
                "⚠️ **Bot Restart Hua Tha!**\n"
                "Aapka purana session expire ho gaya hai.\n\n"
                "Kripya **/index** command dubara shuru karein."
            )
        return

    # Agar step galat hai to return
    if INDEX_SESSION[user_id]['step'] != 'waiting_skip':
        return

    try:
        skip_num = int(text)
    except ValueError:
        return await message.reply("❌ Kripya sirf number likhein (Ex: 0).")

    session = INDEX_SESSION[user_id]
    session['skip'] = skip_num
    session['step'] = 'waiting_confirm'

    total_files = session['last_msg_id'] - skip_num
    
    print(f"DEBUG: Skip Confirmed: {skip_num}. Total to scan: {total_files}") # Debug Log

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Start Indexing", callback_data="idx_start"),
            InlineKeyboardButton("❌ Cancel", callback_data="idx_cancel")
        ]
    ])

    await message.reply_text(
        f"📊 **Indexing Summary**\n\n"
        f"📤 **Channel ID:** `{session['channel_id']}`\n"
        f"🔢 **Last Msg ID:** `{session['last_msg_id']}`\n"
        f"⏭ **Skip:** `{skip_num}`\n"
        f"📂 **Approx Total:** `{total_files}`\n\n"
        "Kya start karein?",
        reply_markup=buttons
    )

# ==========================================
# STEP 4: CORE INDEXING PROCESS
# ==========================================
@Client.on_callback_query(filters.regex(r"^idx_"))
async def index_process_handler(bot: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "idx_cancel":
        if user_id in INDEX_SESSION: del INDEX_SESSION[user_id]
        await query.message.edit("❌ Process Cancelled.")
        return

    if user_id not in INDEX_SESSION:
        return await query.answer("⚠️ Session Expired. /index dubara karein.", show_alert=True)

    # Load Data
    session = INDEX_SESSION[user_id]
    chat_id = session['channel_id']
    last_msg_id = session['last_msg_id']
    current_id = session['skip'] + 1
    
    # Session Clean
    del INDEX_SESSION[user_id]

    msg = await query.message.edit("⏳ **Initializing...**")

    total_scanned = 0
    indexed_files = 0
    duplicate_files = 0
    deleted_msgs = 0
    
    CHUNK_SIZE = 200

    try:
        while current_id <= last_msg_id:
            end_id = min(current_id + CHUNK_SIZE - 1, last_msg_id)
            ids_to_fetch = list(range(current_id, end_id + 1))
            
            if not ids_to_fetch: break

            try:
                # Messages Fetch
                messages = await bot.get_messages(chat_id, ids_to_fetch)
            except FloodWait as e:
                await asyncio.sleep(e.value + 5)
                messages = await bot.get_messages(chat_id, ids_to_fetch)
            except Exception as e:
                print(f"Fetch Error: {e}")
                current_id += CHUNK_SIZE
                continue

            for m in messages:
                total_scanned += 1
                if not m or m.empty:
                    deleted_msgs += 1
                    continue
                
                # Check Media
                if m.document or m.video or m.audio:
                    try:
                        # ⚠️ DB SAVE CHECK
                        is_saved = await db.save_file(m)
                        if is_saved: indexed_files += 1
                        else: duplicate_files += 1
                    except Exception as e:
                        print(f"DB Error: {e}")
                else:
                    deleted_msgs += 1

            # Update Status
            try:
                await msg.edit(
                    f"🔄 **Indexing...**\n"
                    f"Scanned: {total_scanned}/{last_msg_id}\n"
                    f"Saved: {indexed_files}\n"
                    f"Duplicates: {duplicate_files}"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except MessageNotModified:
                pass
            except Exception:
                pass

            current_id += CHUNK_SIZE

        await msg.edit(
            f"✅ **Indexing Complete!**\n\n"
            f"💾 Saved: `{indexed_files}`\n"
            f"♻️ Duplicates: `{duplicate_files}`\n"
            f"🗑 Empty/Skip: `{deleted_msgs}`"
        )

    except Exception as e:
        await msg.edit(f"❌ Error: {e}")
