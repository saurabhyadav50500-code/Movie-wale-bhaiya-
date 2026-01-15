from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from database.ia_filterdb import db

# --- DELETE ALL COMMAND ---
@Client.on_message(filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_confirm(bot, message):
    """
    Admin se confirmation lega.
    """
    await message.reply_text(
        text=(
            "⚠️ **WARNING: Kya aap Saara Data Delete karna chahte hain?**\n\n"
            "(Index ki gai sabhi files delete ho jayengi, lekin Search JSON settings safe rahengi)"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🧨 Delete All", callback_data="delete_all_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="delete_all_no")
            ]
        ]),
        quote=True
    )

# --- CALLBACK HANDLER ---
@Client.on_callback_query(filters.regex(r"^delete_all_"))
async def delete_callback(bot, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    
    # Security Check
    if user_id not in ADMINS:
        return await query.answer("Sirf Admin ye kar sakta hai!", show_alert=True)

    # Cancel Logic
    if data == "delete_all_no":
        await query.message.edit("❌ **Process Cancelled.**\nKoi file delete nahi hui.")
        return

    # Delete Logic
    if data == "delete_all_yes":
        await query.message.edit("⏳ **Deleting All Files...**\n(Please wait, JSON Index safe rahega...)")
        
        try:
            # Database call
            await db.delete_all_files()
            
            # Double check count
            total = await db.col.count_documents({})
            
            if total == 0:
                await query.message.edit(
                    "🗑️ **SUCCESSFULLY DELETED!**\n\n"
                    "✅ Saari indexed files delete ho gayi hain.\n"
                    "✅ **JSON Index SAFE hai.**\n"
                    "🚀 Aap wapas `/index` kar sakte hain."
                )
            else:
                await query.message.edit(f"⚠️ Error: Kuch files delete nahi hui. Remaining: {total}")
                
        except Exception as e:
            await query.message.edit(f"❌ Error aagaya: {str(e)}")
