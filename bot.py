from pyrogram import Client, filters
import os

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

app = Client(
    "movie_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 Welcome!\n"
        "Mai Movie Info Bot hoon 🎬"
    )

@app.on_message(filters.text & ~filters.command)
async def text_handler(client, message):
    await message.reply_text("Text mila 👍")

app.run()
