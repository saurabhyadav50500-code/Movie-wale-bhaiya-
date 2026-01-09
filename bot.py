from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN

# Client initialize karein
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- 1. START COMMAND HANDLER ---
@app.on_message(filters.command("start"))
async def start_command(client, message):
    # Bot ka username fetch karte hain taaki group add link ban sake
    bot_info = await client.get_me()
    username = bot_info.username
    
    # Photo ka URL (Yahan aap apni pasand ki photo ka link daal sakte hain)
    # Ya agar file local hai to "photo.jpg" likh sakte hain
    IMG_URL = "https://graph.org/file/5d8a6e843c0818276f625.jpg"

    # Buttons define karte hain
    buttons = InlineKeyboardMarkup([
        [
            # Button 1: Add to Group (URL Button)
            InlineKeyboardButton(
                text="Add me to group",
                url=f"http://t.me/{username}?startgroup=true"
            )
        ],
        [
            # Button 2: About (Callback Button)
            InlineKeyboardButton(
                text="About",
                callback_data="about_section"
            )
        ]
    ])

    # Photo ke saath message bhejna
    await message.reply_photo(
        photo=IMG_URL,
        caption="**Hello!** 👋\nMain ek Python bot hu. Niche diye gaye buttons se mujhe group me add karein.",
        reply_markup=buttons
    )


# --- 2. CALLBACK HANDLER (About Button ke liye) ---
@app.on_callback_query(filters.regex("about_section"))
async def about_callback(client, callback_query):
    # Jab user "About" button dabayega to ye function chalega
    
    about_text = (
        "🤖 **About Me:**\n\n"
        "Name: My Super Bot\n"
        "Language: Python (Pyrogram)\n"
        "Developer: Aapka Naam\n"
        "Status: V1.0 Running"
    )
    
    # Pehle button click ko acknowledge karein (Loading circle hatane ke liye)
    await callback_query.answer("Details niche bheji gayi hain!")
    
    # User ko text message bhejein
    await callback_query.message.reply_text(about_text)


# --- 3. PURANA LOGIC (Hii wala - Optional) ---
@app.on_message(filters.text & filters.regex(r"(?i)^hii$"))
async def respond_to_hii(client, message):
    await message.reply_text("Hello dear! Kaise ho?")


# --- BOT RUN ---
print("Bot start ho gaya hai...")
app.run()
