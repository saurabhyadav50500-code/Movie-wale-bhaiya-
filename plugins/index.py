import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

# Temporary dictionary to store user session steps
INDEX_SESSION = {}

@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def start_index_step1(bot: Client, message: Message):
    """
    Step 1: Command receive karne ke baad user se last message forward karne ko kahega.
    """
    user_id = message.from_user.id
    
    INDEX_SESSION[user_id] = {'step': 'waiting_forward'}
    
    await message.reply_text(
        "🆔 **Step 1:**\n\n"
        "Apne Channel se **Last Message** (jo sabse latest upload ho) forward kijiye.\n"
        "Ensure karein ki main us channel me Admin hoon."
    )

@Client.on_message(filters.forwarded & filters.user(ADMINS))
async def handle_forward_step2(bot: Client, message: Message):
    """
    Step 2: Forwarded message se Channel ID aur Message ID detect karega.
    """
    user_id = message.from_user.id
    
    if user_id not in INDEX_SESSION or INDEX_SESSION[user_id]['step'] != 'waiting_forward':
        return

    if not message.forward_from_chat:
        return await message.reply("❌ Ye message kisi channel se forwarded nahi lag raha. Kripya channel se forward karein.")

    target_chat_id = message.forward_from_chat.id
    last_msg_id = message.forward_from_message_id

    INDEX_SESSION[user_id].update({
        'step': 'waiting_skip',
        'channel_id': target_chat_id,
        'last_msg_id': last_msg_id
    })

    await message.reply_text(
        f"✅ **Detected!**\n"
        f"Last ID: `{last_msg_id}`\n\n"
        "**Step 2:**\n"
        "Skip Number bhejein (e.g. `0` agar shuru se karna hai)."
    )

@Client.on_message(filters.text & filters.user(ADMINS) & ~filters.command(["index", "batch", "start"]))
async def handle_skip_step3(bot: Client, message: Message):
    """
    Step 3: Skip number set karega aur Confirmation Buttons dikhayega.
    """
    user_id = message.from_user.id
    
    if user_id not in INDEX_SESSION or INDEX_SESSION[user_id]['step'] != 'waiting_skip':
        return

    try:
        skip_num = int(message.text)
    except ValueError:
        return await message.reply("❌ Kripya valid number bhejein (e.g., 0).")

    session_data = INDEX_SESSION[user_id]
    session_data['skip'] = skip_num
    session_data['step'] = 'waiting_confirm'

    last_id = session_data['last_msg_id']
    total_to_process = last_id - skip_num

    if total_to_process <= 0:
        return await message.reply("❌ Skip number Last ID se bada nahi ho sakta.")

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Index Start", callback_data="start_indexing"),
            InlineKeyboardButton("❌ Close", callback_data="cancel_indexing")
        ]
    ])

    await message.reply_text(
        f"**Indexing Confirmation**\n\n"
        f"📤 **Channel ID:** `{session_data['channel_id']}`\n"
        f"🔢 **Last Message ID:** `{last_id}`\n"
        f"⏭ **Skip:** `{skip_num}`\n"
        f"📂 **Total Msgs to Scan:** `{total_to_process}`\n\n"
        "Kya aap indexing start karna chahte hain?",
        reply_markup=buttons
    )

@Client.on_callback_query(filters.regex("^start_indexing") | filters.regex("^cancel_indexing"))
async def index_callback_handler(bot: Client, query: CallbackQuery):
    """
    Buttons handle karega aur Indexing Process chalayega.
    """
    user_id = query.from_user.id
    data = query.data

    if data == "cancel_indexing":
        if user_id in INDEX_SESSION:
            del INDEX_SESSION[user_id]
        await query.message.edit("❌ Indexing Process Cancelled.")
        return

    if user_id not in INDEX_SESSION:
        return await query.answer("Session expired. Dobara /index try karein.", show_alert=True)

    session = INDEX_SESSION[user_id]
    chat_id = session['channel_id']
    last_msg_id = session['last_msg_id']
    skip = session['skip']
    
    del INDEX_SESSION[user_id]

    await query.message.edit("⏳ **Indexing Start ho rahi hai...**\nKripya wait karein.")

    # --- INDEXING LOGIC ---
    
    total_scanned = 0
    indexed_files = 0   # Saved
    duplicate_files = 0 # Already in DB
    skipped_files = 0   # Text, Photos, Stickers etc.
    
    current_id = skip + 1
    chunk_size = 200
    
    try:
        while current_id <= last_msg_id:
            end_id = min(current_id + chunk_size - 1, last_msg_id)
            ids_to_fetch = list(range(current_id, end_id + 1))
            
            if not ids_to_fetch:
                break

            messages = await bot.get_messages(chat_id, ids_to_fetch)
            
            for msg in messages:
                if not msg or msg.empty:
                    continue
                
                total_scanned += 1

                # 👇 FILTER: Sirf Video, Audio, Document ko index karega
                # Photo, Sticker, Text ko SKIP karega
                if msg.document or msg.video or msg.audio:
                    try:
                        # db.save_file automatically duplicate check karta hai
                        # agar duplicate hai to False return karega
                        is_saved = await db.save_file(msg)
                        if is_saved:
                            indexed_files += 1
                        else:
                            duplicate_files += 1
                    except Exception as e:
                        print(f"Error saving: {e}")
                        skipped_files += 1
                else:
                    # Agar photo/text/sticker hai
                    skipped_files += 1
            
            # Progress Update (Har 200 messages ke baad)
            try:
                await query.message.edit(
                    f"**Indexing in Progress...** 🔄\n\n"
                    f"🔢 **Total Scanned:** {current_id} / {last_msg_id}\n"
                    f"✅ **Saved:** {indexed_files}\n"
                    f"♻️ **Duplicates:** {duplicate_files}\n"
                    f"🚫 **Skipped (Photo/Text):** {skipped_files}"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass
            
            current_id += chunk_size
        
        # Final Message
        await query.message.edit(
            f"✅ **Indexing Completed!**\n\n"
            f"📊 **Total Scanned:** {total_scanned}\n"
            f"💾 **Saved:** {indexed_files}\n"
            f"♻️ **Duplicates:** {duplicate_files}\n"
            f"🚫 **Others (Skipped):** {skipped_files}"
        )

    except Exception as e:
        await query.message.edit(f"❌ Error aagaya: {str(e)}")
