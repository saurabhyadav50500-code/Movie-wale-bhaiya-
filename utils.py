# utils.py

import base64
import uuid
import secrets
import string
from pyrogram.types import Message

def generate_link_id(length=8):
    """Generates a unique alphanumeric ID."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def get_file_details(message: Message):
    """
    Extracts file_id, file_ref, name, size, and type from a Message.
    """
    media = None
    file_type = None
    file_name = None
    mime_type = None

    if message.document:
        media = message.document
        file_type = "document"
        file_name = message.document.file_name
        mime_type = message.document.mime_type
    elif message.video:
        media = message.video
        file_type = "video"
        file_name = message.video.file_name or "Unknown Video"
        mime_type = message.video.mime_type
    elif message.audio:
        media = message.audio
        file_type = "audio"
        file_name = message.audio.file_name or "Unknown Audio"
        mime_type = message.audio.mime_type
    
    if not media:
        return None

    return {
        'file_id': media.file_id,
        'file_unique_id': media.file_unique_id,
        'file_ref': getattr(media, "file_ref", ""), # Safe get
        'file_name': file_name,
        'file_size': media.file_size,
        'file_type': file_type,
        'mime_type': mime_type
    }
