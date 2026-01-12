import secrets
import string
from pyrogram.types import Message

def get_size(size):
    """
    Converts bytes to a human-readable format (e.g., 1024 -> 1KB).
    """
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

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
        'file_ref': getattr(media, "file_ref", ""),
        'file_name': file_name,
        'file_size': media.file_size,
        'file_type': file_type,
        'mime_type': mime_type
    }
