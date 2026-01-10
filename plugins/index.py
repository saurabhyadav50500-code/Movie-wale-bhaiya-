# plugins/index.py

import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from info import ADMINS
from database.ia_filterdb import db

# Compile regex for extracting message IDs from links
# Matches: https://t.me/c/CHANNEL_ID/MESSAGE_ID
LINK_PATTERN = re.compile(r"https://t.me/c/(\d+)/(\d+)")

@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def index_channel(bot: Client, message: Message):
    """
    Index all files in the channel where the command is sent.
    """
    chat_id = message.chat.id
    
    # Send initial status message
    status_msg = await message.reply_text("Processing... Starting Indexing.")
    
    total_files = 0
    indexed_files = 0
    duplicate_files = 0
    
    try:
        # Iterate through history (reverse=True means start from oldest to newest if preferred, 
        # but default is newest to oldest. We usually just want to grab everything).
        async for msg in bot.get_chat_history(chat_id):
            # Check if message contains relevant media
            if msg.document or msg.video or msg.audio:
                total_files += 1
                try:
                    is_saved = await db.save_file(msg)
                    if is_saved:
                        indexed_files += 1
                    else:
                        duplicate_files += 1
                except Exception as e:
                    print(f"Error saving file: {e}")
                
                # Update progress every 20 files to avoid FloodWait
                if total_files % 20 == 0:
                    try:
                        await status_msg.edit(
                            f"**Indexing in Progress...**\n\n"
                            f"Total Scanned: {total_files}\n"
                            f"Saved: {indexed_files}\n"
                            f"Duplicates: {duplicate_files}"
                        )
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception:
                        pass
        
        await status_msg.edit(
            f"**Indexing Completed!**\n\n"
            f"Total Scanned: {total_files}\n"
            f"Saved: {indexed_files}\n"
            f"Duplicates: {duplicate_files}"
        )

    except Exception as e:
        await status_msg.edit(f"Error: {str(e)}")


@Client.on_message(filters.command("batch") & filters.user(ADMINS))
async def batch_index(bot: Client, message: Message):
    """
    Index files from a specific range of links.
    Usage: /batch https://t.me/c/..100 https://t.me/c/..200
    """
    if len(message.command) < 3:
        return await message.reply("Usage: `/batch start_link end_link`")

    start_link = message.command[1]
    end_link = message.command[2]

    # Extract info from links
    start_match = LINK_PATTERN.search(start_link)
    end_match = LINK_PATTERN.search(end_link)

    if not start_match or not end_match:
        return await message.reply("Invalid link format. Use private channel links.")

    # Convert channel ID to proper format (add -100 prefix for private channels)
    # The regex captures the ID without -100, usually needed for get_messages if using integer ID
    chat_id_str = start_match.group(1)
    chat_id = int(f"-100{chat_id_str}")
    
    start_msg_id = int(start_match.group(2))
    end_msg_id = int(end_match.group(2))

    if start_msg_id > end_msg_id:
        return await message.reply("Start message ID must be smaller than End message ID.")

    status_msg = await message.reply_text(f"Starting Batch Indexing from {start_msg_id} to {end_msg_id}...")

    # Generate the list of message IDs to fetch
    message_ids = list(range(start_msg_id, end_msg_id + 1))
    
    total_files = 0
    indexed_files = 0
    duplicate_files = 0
    
    # Process in chunks of 200 (Pyrogram get_messages limit)
    chunk_size = 200
    
    try:
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i:i + chunk_size]
            messages = await bot.get_messages(chat_id, chunk)
            
            for msg in messages:
                if not msg or msg.empty: 
                    continue
                
                if msg.document or msg.video or msg.audio:
                    total_files += 1
                    try:
                        is_saved = await db.save_file(msg)
                        if is_saved:
                            indexed_files += 1
                        else:
                            duplicate_files += 1
                    except Exception as e:
                        print(f"Error saving batch file: {e}")

            # Update Progress
            try:
                await status_msg.edit(
                    f"**Batch Indexing...**\n\n"
                    f"Processed: {i + len(chunk)} / {len(message_ids)}\n"
                    f"Saved: {indexed_files}\n"
                    f"Duplicates: {duplicate_files}"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass
        
        await status_msg.edit(
            f"**Batch Indexing Completed!**\n\n"
            f"Total Scanned: {total_files}\n"
            f"Saved: {indexed_files}\n"
            f"Duplicates: {duplicate_files}"
        )

    except Exception as e:
        await status_msg.edit(f"Error occurred: {str(e)}")
