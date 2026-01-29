import secrets
import string
import re
import math
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 1. SMART DETECTION PATTERNS (Regex)
# ==========================================

# Matches: "Hindi", "Hin", "HIN", "dub", "Dual" (Case Insensitive)
LANG_PATTERNS = {
    "Hindi": re.compile(r'\b(hindi|hin|dub|dual|org)\b', re.IGNORECASE),
    "English": re.compile(r'\b(english|eng)\b', re.IGNORECASE),
    "Tamil": re.compile(r'\b(tamil|tam)\b', re.IGNORECASE),
    "Telugu": re.compile(r'\b(telugu|tel)\b', re.IGNORECASE),
    "Malayalam": re.compile(r'\b(malayalam|mal)\b', re.IGNORECASE),
    "Kannada": re.compile(r'\b(kannada|kan)\b', re.IGNORECASE),
}

# Matches: "720p", "720", "HD"
QUAL_PATTERNS = {
    "480p": re.compile(r'\b(480p|480|sd)\b', re.IGNORECASE),
    "720p": re.compile(r'\b(720p|720|hd)\b', re.IGNORECASE),
    "1080p": re.compile(r'\b(1080p|1080|fhd)\b', re.IGNORECASE),
    "4k": re.compile(r'\b(2160p|4k|uhd)\b', re.IGNORECASE),
}

# ==========================================
# 2. GENERAL UTILITIES
# ==========================================

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

# ==========================================
# 3. SMART BUTTON PARSER
# ==========================================

async def btn_parser(search_id, files, client, offset=0, active_lang=None, active_qual=None):
    """
    Generates buttons with Smart Language & Quality Filters.
    
    Callback Data Format: 
    action_searchID_offset_lang_qual
    e.g. next_123_10_hindi_720p
    """
    buttons = []
    
    # Username safe fetch
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot"

    # --- A. FILE LIST ---
    if not files:
        # ⚠️ HANDLE ZERO RESULTS: Show dummy button so filters don't vanish
        buttons.append([InlineKeyboardButton("🤷‍♂️ No files found (Try changing filters)", callback_data="none")])
    else:
        for file in files:
            f_id = file.get('link_id')
            f_name = file.get('file_name', 'Unknown File')
            f_size = get_size(file.get('file_size', 0))
            
            # Smart Truncate to keep buttons neat
            if len(f_name) > 30:
                f_name = f_name[:27] + "..."
                
            buttons.append([InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )])

    # --- B. LANGUAGE FILTER ROW ---
    lang_row = []
    # You can add more languages here
    langs = ["Hindi", "English", "Tamil", "Telugu"] 
    
    for lang in langs:
        # Check if this language is currently active
        is_active = (active_lang == lang.lower())
        
        # Toggle Logic: Click Active -> Reset to None | Click Inactive -> Set to Lang
        text = f"✅ {lang}" if is_active else lang
        new_lang = "None" if is_active else lang.lower()
        
        # Preserve the current Quality state (active_qual)
        # Data: filter_ID_Offset_Lang_Qual
        current_qual_str = active_qual if active_qual else "None"
        cb_data = f"filter_{search_id}_0_{new_lang}_{current_qual_str}"
        
        lang_row.append(InlineKeyboardButton(text, callback_data=cb_data))
    
    buttons.append(lang_row)

    # --- C. QUALITY FILTER ROW ---
    qual_row = []
    quals = ["480p", "720p", "1080p"]
    
    for qual in quals:
        is_active = (active_qual == qual.lower())
        
        text = f"✅ {qual}" if is_active else qual
        new_qual = "None" if is_active else qual.lower()
        
        # Preserve the current Language state (active_lang)
        current_lang_str = active_lang if active_lang else "None"
        cb_data = f"filter_{search_id}_0_{current_lang_str}_{new_qual}"
        
        qual_row.append(InlineKeyboardButton(text, callback_data=cb_data))

    buttons.append(qual_row)

    # --- D. PAGINATION ---
    # Format: next_ID_Offset_Lang_Qual
    
    total_files = len(files) if files else 0
    # Note: If 0 files, we still might show pagination buttons if offset > 0 (handled by logic outside)
    
    nav_buttons = []
    
    # Strings for callback
    cb_lang = active_lang if active_lang else "None"
    cb_qual = active_qual if active_qual else "None"

    # Back Button
    if offset >= 10:
        nav_buttons.append(
            InlineKeyboardButton(
                "⬅️ Back", 
                callback_data=f"next_{search_id}_{offset - 10}_{cb_lang}_{cb_qual}"
            )
        )

    # Page Counter (Non-clickable)
    current_page = math.ceil(offset / 10) + 1
    nav_buttons.append(
        InlineKeyboardButton(f"Page {current_page}", callback_data="pages")
    )

    # Next Button (Only if we have full page of results)
    if total_files >= 10:
        nav_buttons.append(
            InlineKeyboardButton(
                "Next ➡️", 
                callback_data=f"next_{search_id}_{offset + 10}_{cb_lang}_{cb_qual}"
            )
        )

    buttons.append(nav_buttons)

    # Close Button
    buttons.append([InlineKeyboardButton("♻️ Close", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)
