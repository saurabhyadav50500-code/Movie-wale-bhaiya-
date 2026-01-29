import secrets
import string
import re
import math
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# 👇 Database Import (Required for Smart Year Detection)
from database.ia_filterdb import db

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
# 2. GENERAL UTILITIES (Old Code Preserved)
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
# 3. SMART BUTTON PARSER (Updated for 4 Layers)
# ==========================================

async def btn_parser(search_id, files, client, offset=0, active_lang=None, active_qual=None, active_year=None, active_size=None):
    """
    Generates buttons with 4 Layers of Filters: Lang, Qual, Year, Size.
    
    Callback Data Format: 
    action_searchID_offset_lang_qual_year_size
    """
    buttons = []
    
    # Username safe fetch
    if client.me:
        bot_username = client.me.username
    else:
        bot_username = "my_random_bot"

    # --- A. FILE LIST ---
    if not files:
        # ⚠️ HANDLE ZERO RESULTS
        buttons.append([InlineKeyboardButton("🤷‍♂️ No files found (Try changing filters)", callback_data="none")])
    else:
        for file in files:
            f_id = file.get('link_id')
            f_name = file.get('file_name', 'Unknown File')
            f_size = get_size(file.get('file_size', 0))
            
            if len(f_name) > 30:
                f_name = f_name[:27] + "..."
                
            buttons.append([InlineKeyboardButton(
                text=f"📂 {f_name} | {f_size}",
                url=f"https://t.me/{bot_username}?start=file_{f_id}"
            )])

    # Helper for Safe Callback Strings (Avoid 'None' object error)
    c_lang = active_lang if active_lang else "None"
    c_qual = active_qual if active_qual else "None"
    c_year = active_year if active_year else "None"
    c_size = active_size if active_size else "None"

    # --- B. LANGUAGE ROW ---
    lang_row = []
    langs = ["Hindi", "English", "Tamil"] 
    
    for lang in langs:
        l_code = lang.lower()
        is_active = (active_lang == l_code)
        
        text = f"✅ {lang}" if is_active else lang
        next_val = "None" if is_active else l_code # Toggle Logic
        
        # Reset offset to 0 when filter changes
        cb_data = f"filter_{search_id}_0_{next_val}_{c_qual}_{c_year}_{c_size}"
        lang_row.append(InlineKeyboardButton(text, callback_data=cb_data))
    
    buttons.append(lang_row)

    # --- C. QUALITY ROW ---
    qual_row = []
    quals = ["480p", "720p", "1080p"]
    
    for qual in quals:
        q_code = qual.lower()
        is_active = (active_qual == q_code)
        
        text = f"✅ {qual}" if is_active else qual
        next_val = "None" if is_active else q_code
        
        cb_data = f"filter_{search_id}_0_{c_lang}_{next_val}_{c_year}_{c_size}"
        qual_row.append(InlineKeyboardButton(text, callback_data=cb_data))

    buttons.append(qual_row)

    # --- D. YEAR ROW (Smart Detection) ---
    # Fetch available years from DB for this query
    query = await db.get_search_query(search_id)
    available_years = await db.get_unique_years(query) if query else []
    
    year_row = []
    # Show max 4 relevant years to save space
    for year in available_years[:4]: 
        is_active = (active_year == year)
        
        text = f"✅ {year}" if is_active else year
        next_val = "None" if is_active else year
        
        cb_data = f"filter_{search_id}_0_{c_lang}_{c_qual}_{next_val}_{c_size}"
        year_row.append(InlineKeyboardButton(text, callback_data=cb_data))
    
    if year_row:
        buttons.append(year_row)

    # --- E. SIZE ROW ---
    # Keys: s (<500), m (500-1G), l (1G-2G), xl (>2G)
    size_row = []
    sizes = [("s", "<500MB"), ("m", "1GB"), ("l", "2GB"), ("xl", ">2GB")]
    
    for key, label in sizes:
        is_active = (active_size == key)
        
        text = f"✅ {label}" if is_active else label
        next_val = "None" if is_active else key
        
        cb_data = f"filter_{search_id}_0_{c_lang}_{c_qual}_{c_year}_{next_val}"
        size_row.append(InlineKeyboardButton(text, callback_data=cb_data))
    
    buttons.append(size_row)

    # --- F. PAGINATION ---
    nav_buttons = []
    
    # Back Button
    if offset >= 10:
        nav_buttons.append(
            InlineKeyboardButton(
                "⬅️ Back", 
                callback_data=f"next_{search_id}_{offset - 10}_{c_lang}_{c_qual}_{c_year}_{c_size}"
            )
        )

    # Page Number
    current_page = math.ceil(offset / 10) + 1
    nav_buttons.append(InlineKeyboardButton(f"Page {current_page}", callback_data="pages"))

    # Next Button (Only if we have full page)
    if len(files) >= 10:
        nav_buttons.append(
            InlineKeyboardButton(
                "Next ➡️", 
                callback_data=f"next_{search_id}_{offset + 10}_{c_lang}_{c_qual}_{c_year}_{c_size}"
            )
        )

    buttons.append(nav_buttons)

    # Close Button
    buttons.append([InlineKeyboardButton("♻️ Close / Wrong Result", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)
