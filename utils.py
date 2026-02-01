import re
import math
import secrets
import string
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 1. REGEX PATTERNS (Don't remove these)
# ==========================================
LANG_PATTERNS = {
    "Hindi": re.compile(r'\b(hindi|hin|dub|dual)\b', re.IGNORECASE),
    "English": re.compile(r'\b(english|eng)\b', re.IGNORECASE),
    "Tamil": re.compile(r'\b(tamil|tam)\b', re.IGNORECASE),
    "Telugu": re.compile(r'\b(telugu|tel)\b', re.IGNORECASE),
}

QUAL_PATTERNS = {
    "480p": re.compile(r'\b(480p|480|sd)\b', re.IGNORECASE),
    "720p": re.compile(r'\b(720p|720|hd)\b', re.IGNORECASE),
    "1080p": re.compile(r'\b(1080p|1080|fhd)\b', re.IGNORECASE),
    "4k": re.compile(r'\b(2160p|4k|uhd)\b', re.IGNORECASE),
}

# ==========================================
# 2. HELPER FUNCTIONS (Important for Save File)
# ==========================================
def get_file_details(message):
    """Extracts media details from a message."""
    media = message.document or message.video or message.audio
    if not media: return None
    return {
        'file_id': media.file_id,
        'file_unique_id': media.file_unique_id,
        'file_name': media.file_name or "Unknown",
        'file_size': media.file_size,
        'file_type': "video" if message.video else "audio" if message.audio else "document",
        'mime_type': media.mime_type
    }

def get_size(size):
    """Converts bytes to human readable size."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def generate_link_id(length=8):
    """Generates a random link ID."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# ==========================================
# 3. BUTTON PARSER (The Layout Logic)
# ==========================================
async def btn_parser(search_id, files, client, offset, a_type=None, a_lang=None, a_qual=None, a_year=None, a_size=None, years=None):
    """
    Generates the Inline Buttons Layout.
    Arguments:
    - years: List of years passed from autofilter.py (No DB call here to avoid circular import)
    """
    buttons = []
    
    # --- ROW 1: FILE RESULTS ---
    bot_username = client.me.username if client.me else "Bot"
    if not files:
         buttons.append([InlineKeyboardButton("🤷‍♂️ No results with these filters", callback_data="none")])
    else:
        for file in files:
            f_name = file['file_name']
            f_size = get_size(file['file_size'])
            f_link = f"https://t.me/{bot_username}?start=file_{file['link_id']}"
            
            # Shorten name to fit button
            if len(f_name) > 30: f_name = f_name[:27] + "..."
            
            buttons.append([InlineKeyboardButton(f"📂 {f_name} | {f_size}", url=f_link)])

    # Helper function to handle None values in callback string
    def s(val): return val if val else "None"
    
    # Base Callback Format: filter_ID_Offset_Type_Lang_Qual_Year_Size
    # Note: Reset offset to 0 when changing filters
    base = f"filter_{search_id}_0"

    # --- ROW 2: TYPE FILTERS (Video | Docs | Reset) ---
    type_row = []
    for t in ["video", "document"]:
        label = "📹 Videos" if t == "video" else "📂 Docs"
        if a_type == t:
            label = f"✅ {label.split()[1]}" # Show Checkmark
            new_val = "None" # Uncheck if clicked again
        else:
            new_val = t
        
        # Keep other filters (lang, qual, etc) as they are
        type_row.append(InlineKeyboardButton(label, callback_data=f"{base}_{new_val}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"))
    
    # Reset Button (Visible if any filter is active)
    if any([a_type, a_lang, a_qual, a_year, a_size]):
         type_row.append(InlineKeyboardButton("🔄 Reset", callback_data=f"{base}_None_None_None_None_None"))
    buttons.append(type_row)

    # --- ROW 3: LANGUAGE & QUALITY (Mixed) ---
    lq_row = []
    # Languages
    for lang in ["Hindi", "English"]:
        l_code = lang.lower()
        txt = f"✅ {lang}" if a_lang == l_code else lang
        n_l = "None" if a_lang == l_code else l_code
        lq_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{n_l}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"))
    
    # Qualities
    for qual in ["720p", "1080p"]:
        q_code = qual.lower()
        txt = f"✅ {qual}" if a_qual == q_code else qual
        n_q = "None" if a_qual == q_code else q_code
        lq_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{n_q}_{s(a_year)}_{s(a_size)}"))
    
    buttons.append(lq_row)

    # --- ROW 4: YEARS & SIZE (Mixed) ---
    ys_row = []
    
    # Years (Dynamic list passed from autofilter.py)
    available_years = years if years else []
    for year in available_years[:2]: # Show max 2 relevant years
        txt = f"✅ {year}" if a_year == year else year
        n_y = "None" if a_year == year else year
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{n_y}_{s(a_size)}"))

    # Sizes
    sizes = [("s", "<500MB"), ("l", "1GB+")]
    for k, v in sizes:
        txt = f"✅ {v}" if a_size == k else v
        n_s = "None" if a_size == k else k
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{n_s}"))
    
    buttons.append(ys_row)

    # --- ROW 5: PAGINATION ---
    nav = []
    # Use current state for pagination
    cb_state = f"{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"
    
    if offset >= 10:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"next_{search_id}_{offset-10}_{cb_state}"))
    
    nav.append(InlineKeyboardButton(f"Page {math.ceil(offset/10)+1}", callback_data="pages"))
    
    if len(files) >= 10:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{search_id}_{offset+10}_{cb_state}"))
    
    buttons.append(nav)
    
    # Close Button
    buttons.append([InlineKeyboardButton("♻️ Close", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)
