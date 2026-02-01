import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

# Session Storage (Bot restart hone par ye khali ho jata hai)
INDEX_SESSION = {}

# ==========================================
# STEP 1: INITIAL COMMAND
# ==========================================
@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def start_index_step1(bot: Client, message: Message):
    """Admin se last message maangta hai."""
    user_id = message.from_user.id
    INDEX_SESSION[user_id] = {'step': 'waiting_forward'}
    
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
    """Forwarded message se Channel ID aur Message ID nikalta hai."""
    user_id = message.from_user.id
    
    # Check if user is in session
    if user_id not in INDEX_SESSION or INDEX_SESSION[user_id]['step'] != 'waiting_forward':
        return

    if not message.forward_from_chat:
        return await message.reply("❌ Ye Message Channel se forwarded nahi lag raha.")

    # Data Extract
    target_chat_id = message.forward_from_chat.id
    last_msg_id = message.forward_from_message_id

    # Update Session
    INDEX_SESSION[user_id].update({
        'step': 'waiting_skip',
        'channel_id': target_chat_id,
        'last_msg_id': last_msg_id
    })

    await message.reply_text(
        f"✅ **Detected Channel:** `{message.forward_from_chat.title}`\n"
        f"🔢 **Last ID:** `{last_msg_id}`\n\n"
        "**Step 2:** Kitne messages skip karne hain? (Shuru se karne ke liye `0` likhein)."
    )

# ==========================================
# STEP 3: HANDLE SKIP NUMBER (Modified for Safety)
# ==========================================
@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["index", "start", "broadcast"]))
async def handle_skip_step3(bot: Client, message: Message):
    """User se skip number leta hai."""
    user_id = message.from_user.id
    
    # 🛑 SAFETY CHECK: Agar Session expire ho gaya hai to user ko batao
    if user_id not in INDEX_SESSION:
        # Agar user koi number bhej raha hai par session nahi hai, to shayad bot restart hua hai
        if message.text.isdigit():
            await message.reply("⚠️ **Session Expired / Bot Restarted.**\nKripya `/index` command dubara shuru karein.")
        return

    if INDEX_SESSION[user_id]['step'] != 'waiting_skip':
        return

    try:
        skip_num = int(message.text)
    except ValueError:
        return await message.reply("❌ Kripya valid number likhein (Ex: 0).")

    session = INDEX_SESSION[user_id]
    session['skip'] = skip_num
    session['step'] = 'waiting_confirm'

    total_files = session['last_msg_id'] - skip_num

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
# STEP 4: CORE INDEXING LOGIC
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
        return await query.answer("⚠️ Session Expired. Dobara /index karein.", show_alert=True)

    # Load Variables
    session = INDEX_SESSION[user_id]
    chat_id = session['channel_id']
    last_msg_id = session['last_msg_id']
    current_id = session['skip'] + 1
    
    del INDEX_SESSION[user_id] # Clear session to free memory

    msg = await query.message.edit("⏳ **Initializing Indexing...**")

    # Stats
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
                messages = await bot.get_messages(chat_id, ids_to_fetch)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
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
                        # ⚠️ IMPORTANT: Ye call ia_filterdb.py ke save_file ko jata hai
                        is_saved = await db.save_file(m)
                        if is_saved:
                            indexed_files += 1
                        else:
                            duplicate_files += 1
                    except Exception as e:
                        print(f"Save Error: {e}")
                else:
                    deleted_msgs += 1

            # Update Status
            try:
                await msg.edit(
                    f"🔄 **Indexing in Progress...**\n\n"
                    f"🔢 **Scanned:** `{total_scanned}` / `{last_msg_id}`\n"
                    f"💾 **Saved:** `{indexed_files}`\n"
                    f"♻️ **Duplicates:** `{duplicate_files}`\n"
                    f"🗑 **Skipped:** `{deleted_msgs}`"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except MessageNotModified:
                pass
            except Exception:
                pass 

            current_id += CHUNK_SIZE

        # Final Message
        await msg.edit(
            f"✅ **Indexing Completed!**\n\n"
            f"📊 **Scanned:** `{total_scanned}`\n"
            f"💾 **Saved:** `{indexed_files}`\n"
            f"♻️ **Duplicates:** `{duplicate_files}`"
        )

    except Exception as e:
        await msg.edit(f"❌ Critical Error: {str(e)}")
