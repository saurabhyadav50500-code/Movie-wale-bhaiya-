# database/ia_filterdb.py

import motor.motor_asyncio
from info import MONGO_URI, DATABASE_NAME, COLLECTION_NAME
from utils import get_file_details, generate_link_id

class Media:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.col = self.db[COLLECTION_NAME]

    async def save_file(self, media_message):
        """
        Extracts details from a Pyrogram Message and saves it to MongoDB.
        """
        # Extract file details using a helper function
        file_details = get_file_details(media_message)
        if not file_details:
            return False

        # Check for duplicates based on file_unique_id
        is_exist = await self.col.find_one({'file_unique_id': file_details['file_unique_id']})
        if is_exist:
            return False # Duplicate found

        # Generate a unique alphanumeric link_id
        link_id = generate_link_id()

        # Prepare the document
        file_doc = {
            'file_id': file_details['file_id'],
            'file_unique_id': file_details['file_unique_id'], # Store for duplicate check
            'file_ref': file_details['file_ref'],
            'file_name': file_details['file_name'],
            'file_size': file_details['file_size'],
            'file_type': file_details['file_type'],
            'mime_type': file_details['mime_type'],
            'caption': media_message.caption or "",
            'chat_id': media_message.chat.id,
            'message_id': media_message.id,
            'link_id': link_id
        }

        await self.col.insert_one(file_doc)
        return True

# Create an instance to be used in plugins
db = Media()
