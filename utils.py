import re
import math
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- REGEX PATTERNS (Kept here for ia_filterdb to import) ---
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

def get_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

# ==========================================
# 🛠️ BUTTON PARSER (No Database Logic Here)
# ==========================================
async def btn_parser(search_id, files, client, offset, a_type=None, a_lang=None, a_qual=None, a_year=None, a_size=None, years=None):
    """
    Generates buttons. Now accepts 'years' list from autofilter.py.
    """
    buttons = []
    
    # 1. FILES
    bot_username = client.me.username if client.me else "Bot"
    if not files:
         buttons.append([InlineKeyboardButton("🤷‍♂️ No results with these filters", callback_data="none")])
    else:
        for file in files:
            f_name = file['file_name']
            f_size = get_size(file['file_size'])
            f_link = f"https://t.me/{bot_username}?start=file_{file['link_id']}"
            if len(f_name) > 30: f_name = f_name[:27] + "..."
            buttons.append([InlineKeyboardButton(f"📂 {f_name} | {f_size}", url=f_link)])

    # Helper for Safe Strings
    def s(val): return val if val else "None"
    base = f"filter_{search_id}_0"

    # 2. TYPE (Video | Docs)
    type_row = []
    for t in ["video", "document"]:
        label = "📹 Videos" if t == "video" else "📂 Docs"
        if a_type == t:
            label = f"✅ {label.split()[1]}"
            new_val = "None"
        else:
            new_val = t
        type_row.append(InlineKeyboardButton(label, callback_data=f"{base}_{new_val}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"))
    
    if any([a_type, a_lang, a_qual, a_year, a_size]):
         type_row.append(InlineKeyboardButton("🔄 Reset", callback_data=f"{base}_None_None_None_None_None"))
    buttons.append(type_row)

    # 3. LANGUAGE & QUALITY
    lq_row = []
    for lang in ["Hindi", "English"]:
        l_code = lang.lower()
        txt = f"✅ {lang}" if a_lang == l_code else lang
        n_l = "None" if a_lang == l_code else l_code
        lq_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{n_l}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"))
    
    for qual in ["720p", "1080p"]:
        q_code = qual.lower()
        txt = f"✅ {qual}" if a_qual == q_code else qual
        n_q = "None" if a_qual == q_code else q_code
        lq_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{n_q}_{s(a_year)}_{s(a_size)}"))
    buttons.append(lq_row)

    # 4. YEAR & SIZE
    ys_row = []
    
    # Use the passed years list instead of querying DB
    available_years = years if years else []
    
    for year in available_years[:2]: # Show max 2 years
        txt = f"✅ {year}" if a_year == year else year
        n_y = "None" if a_year == year else year
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{n_y}_{s(a_size)}"))

    sizes = [("s", "<500MB"), ("l", "1GB+")]
    for k, v in sizes:
        txt = f"✅ {v}" if a_size == k else v
        n_s = "None" if a_size == k else k
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{n_s}"))
    buttons.append(ys_row)

    # 5. PAGINATION
    nav = []
    cb_state = f"{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"
    
    if offset >= 10:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"next_{search_id}_{offset-10}_{cb_state}"))
    
    nav.append(InlineKeyboardButton(f"Page {math.ceil(offset/10)+1}", callback_data="pages"))
    
    if len(files) >= 10:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_{search_id}_{offset+10}_{cb_state}"))
    
    buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("♻️ Close", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)
