import random
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN

# Bot Client का Initialization
app = Client(
    "my_random_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Random Replies की लिस्ट
REPLY_MESSAGES = [
    "Hello",
    "Hello cutie",
    "Hello Mr",
    "Hello guys",
    "Kaise ho dear"
]

# Message Handler: जब भी कोई text message आए
@app.on_message(filters.text)
async def handle_message(client, message):
    # User का message lowercase में convert करके check करते हैं
    user_text = message.text.lower()
    
    # अगर user ने "hii" भेजा है (exact match)
    if user_text == "hii":
        # Randomly एक reply चुनें
        random_reply = random.choice(REPLY_MESSAGES)
        
        # Reply भेजें
        await message.reply_text(random_reply)

# Bot को Start करें
print("Bot start ho gaya hai...")
app.run()
