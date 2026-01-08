import random
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN
from keep_alive import keep_alive  # <--- Ye line add karein

# Bot Client Initialization
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

REPLY_MESSAGES = [
    "Hello", "Hello cutie", "Hello Mr", "Hello guys", "Kaise ho dear"
]

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_name = message.from_user.mention
    txt = f"👋 Namaste **{user_name}**!\n\nMain ek Random Reply Bot hu. Mujhe **'hii'** likh kar bhejo!"
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/YourUsername")]
    ])
    await message.reply_text(text=txt, reply_markup=buttons)

@app.on_message(filters.text)
async def handle_message(client, message):
    user_text = message.text.lower()
    if user_text == "hii":
        random_reply = random.choice(REPLY_MESSAGES)
        await message.reply_text(random_reply)

print("Bot start ho gaya hai...")

# --- Server Start ---
keep_alive()  # <--- Ye function call karein
# --------------------

app.run()
