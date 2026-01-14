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
            "⚠️ WARNING: Kya aap Saara Data Delete karna chahte hain?\n"
            "(Index ki gai file delete )"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Delete all", callback_data="delete_all_confirm"),
                InlineKeyboardButton("cancel", callback_data="delete_all_cancel")
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
        await query.message.edit("⏳ **Deleting All Files...**\nKripya wait karein...")
        
        try:
            # Database function call karein
            await db.delete_all_files()
            
            await query.message.edit(
                "🗑️ **Successfully Deleted All Files!**\n"
                "Database ab poori tarah khaali (Clean) hai."
            )
        except Exception as e:
            await query.message.edit(f"❌ Error aagaya: {str(e)}")
