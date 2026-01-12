# --- START COMMAND ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # 👇 YE LINE ADD KARNI HAI (Important)
    # Agar start ke baad kuch aur bhi likha hai (jaise file_id), to ye function mat chalao
    if len(message.command) > 1:
        return 

    # Bot ka username nikalein
    bot_info = await client.get_me()
    username = bot_info.username
    
    IMG_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/480px-Python-logo-notext.svg.png"

    # Buttons Setup
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                text="➕ Add me to group",
                url=f"http://t.me/{username}?startgroup=true"
            )
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ About",
                callback_data="about_section"
            )
        ]
    ])

    await message.reply_photo(
        photo=IMG_URL,
        caption=(
            "**Namaste!** 🙏\n\n"
            "Main ek advanced Telegram Bot hu.\n"
            "Mujhe apne group mein add karne ke liye niche button dabayein."
        ),
        reply_markup=buttons
    )
