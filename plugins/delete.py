from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

# --- DELETE ALL COMMAND ---
@Client.on_message(filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_handler(bot, message):
    """
    Admin ko Warning dega ki saara data delete hone wala hai.
    """
    await message.reply_text(
        text=(
            "⚠️ **WARNING: SYSTEM RESET**\n\n"
            "Kya aap sach mein **SAARA DATA** delete karna chahte hain?\n"
            "Isse Index ki gayi **SABHI FILES** delete ho jayengi.\n\n"
            "ℹ️ **Note:** Agar Search kaam nahi kar raha, to ye zaroori hai."
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🧨 YES, DELETE ALL", callback_data="delete_all_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="delete_all_cancel")
            ]
        ]),
        quote=True
    )

# --- BUTTON HANDLER ---
@Client.on_callback_query(filters.regex(r"^delete_all_"))
async def delete_callback_handler(bot, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    
    # Security Check: Sirf Admin hi delete kar sake
    if user_id not in ADMINS:
        return await query.answer("❌ Sirf Admin ye kar sakta hai!", show_alert=True)

    if data == "delete_all_cancel":
        await query.message.delete()
        return

    if data == "delete_all_confirm":
        await query.message.edit("⏳ **Deleting All Files...**\n(Database Cleaning in progress...)")
        
        try:
            # 1. Database Delete Call
            await db.delete_all_files()
            
            # 2. Verification (Check karein ki sach me delete hua ya nahi)
            total_remaining = await db.col.count_documents({})
            
            if total_remaining == 0:
                await query.message.edit(
                    "🗑️ **SUCCESSFULLY DELETED!**\n\n"
                    "✅ Database ab bilkul **KHALI (0 Files)** hai.\n"
                    "🚀 Ab aap `/index` command se dobara Indexing shuru kar sakte hain."
                )
            else:
                await query.message.edit(
                    f"⚠️ **Error:** Delete failed.\n"
                    f"Abhi bhi **{total_remaining}** files bachi hain.\n"
                    "Kripya dobara try karein."
                )
                
        except Exception as e:
            await query.message.edit(f"❌ Error aagaya: {str(e)}")
