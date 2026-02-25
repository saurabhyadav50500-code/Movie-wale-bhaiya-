import re
import math
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- REGEX PATTERNS ---
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

# --- HELPER FUNCTIONS ---
def get_file_details(message):
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
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def generate_link_id(length=8):
    import secrets, string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# ==========================================
# 🛠️ BUTTON PARSER - UPDATED (With Sort & Lang Menu)
# ==========================================
async def btn_parser(search_id, files, client, offset, a_type=None, a_lang=None, a_qual=None, a_year=None, a_size=None, a_sort=None, years=None):
    buttons = []
    
    # Helper to check None
    def s(val): return val if val else "None"
    
    # Base Callback: filter_ID_OFFSET_TYPE_LANG_QUAL_YEAR_SIZE_SORT
    base = f"filter_{search_id}_0"

    # 1. FILE RESULTS
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

    # 2. TYPE BUTTONS
    type_row = []
    for t in ["video", "document"]:
        label = "📹 Videos" if t == "video" else "📂 Docs"
        if a_type == t:
            label = f"✅ {label.split()[1]}"
            new_val = "None"
        else:
            new_val = t
        type_row.append(InlineKeyboardButton(label, callback_data=f"{base}_{new_val}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    
    # Reset Button
    if any([a_type, a_lang, a_qual, a_year, a_size, a_sort]):
         type_row.append(InlineKeyboardButton("🔄 Reset", callback_data=f"{base}_None_None_None_None_None_None"))
    buttons.append(type_row)

    # 3. LANG & QUAL BUTTONS
    lq_row = []
    
    # 🗣️ Select Language Button (Qualities ke bagal me dikhega)
    lang_label = f"{a_lang.title()} ✅" if a_lang and a_lang != "None" else "🗣 Select Language"
    lq_row.append(InlineKeyboardButton(lang_label, callback_data=f"langmenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    
    # Qualities Button
    for qual in ["720p", "1080p"]:
        q_code = qual.lower()
        txt = f"✅ {qual}" if a_qual == q_code else qual
        n_q = "None" if a_qual == q_code else q_code
        lq_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{n_q}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    buttons.append(lq_row)

    # 4. YEARS & SIZE BUTTONS
    ys_row = []
    available_years = years if years else []
    for year in available_years[:2]:
        txt = f"✅ {year}" if a_year == year else year
        n_y = "None" if a_year == year else year
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{n_y}_{s(a_size)}_{s(a_sort)}"))

    sizes = [("s", "<500MB"), ("l", "1GB+")]
    for k, v in sizes:
        txt = f"✅ {v}" if a_size == k else v
        n_s = "None" if a_size == k else k
        ys_row.append(InlineKeyboardButton(txt, callback_data=f"{base}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{n_s}_{s(a_sort)}"))
    buttons.append(ys_row)

    # 5. SORT BUTTON
    current_sort_label = "Relevance"
    if a_sort == "new": current_sort_label = "Newest"
    elif a_sort == "old": current_sort_label = "Oldest"
    elif a_sort == "max": current_sort_label = "Largest"
    elif a_sort == "min": current_sort_label = "Smallest"
    
    buttons.append([
        InlineKeyboardButton(f"📂 Sort: {current_sort_label}", callback_data=f"sortmenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}")
    ])

    # 6. PAGINATION
    nav = []
    cb_state = f"{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    if offset >= 10:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"filter_{search_id}_{offset-10}_{cb_state}"))
    
    nav.append(InlineKeyboardButton(f"Page {math.ceil(offset/10)+1}", callback_data="pages"))
    
    if len(files) >= 10:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"filter_{search_id}_{offset+10}_{cb_state}"))
    
    buttons.append(nav)
    buttons.append([InlineKeyboardButton("♻️ Close", callback_data="recheck_menu")])

    return InlineKeyboardMarkup(buttons)

# ==========================================
# 🆕 SORT MENU GENERATOR
# ==========================================
async def sort_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
    """
    Shows available sort options.
    """
    def s(val): return val if val else "None"
    
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    base_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}"

    buttons = []
    options = [
        ("rel", "Relevance (Default)"),
        ("new", "Newest First"),
        ("old", "Oldest First"),
        ("max", "Largest Size"),
        ("min", "Smallest Size")
    ]
    
    for code, label in options:
        is_active = (code == "rel" and a_sort is None) or (code == a_sort)
        text = f"✅ {label}" if is_active else label
        
        val = "None" if code == "rel" else code
        buttons.append([InlineKeyboardButton(text, callback_data=f"{base_data}_{val}")])

    buttons.append([InlineKeyboardButton("⬅️ Back to Filters", callback_data=back_data)])
    
    return InlineKeyboardMarkup(buttons)

# ==========================================
# 🗣️ LANGUAGE MENU GENERATOR
# ==========================================
async def lang_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
    """
    Shows available language options in a sub-menu.
    """
    def s(val): return val if val else "None"
    
    # Wapas main filter menu par jaane ke liye
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    buttons = []
    options = [
        ("english", "English"), 
        ("hindi", "Hindi"), 
        ("tamil", "Tamil"), 
        ("telugu", "Telugu")
    ]
    
    row = []
    for code, label in options:
        is_active = (code == a_lang)
        text = f"{label} ✅" if is_active else label
        
        # Agar already selected hai aur click kare to deselect ho jaye (None)
        val = "None" if is_active else code
        base_data = f"filter_{search_id}_0_{s(a_type)}_{val}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        
        row.append(InlineKeyboardButton(text, callback_data=base_data))
        
        # Do buttons ek row me
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: 
        buttons.append(row)

    # Agar koi language select ki hui hai to "All Languages" ka option dikhaye
    if a_lang and a_lang != "None":
        all_lang_data = f"filter_{search_id}_0_{s(a_type)}_None_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        buttons.append([InlineKeyboardButton("🌍 All Languages", callback_data=all_lang_data)])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=back_data)])
    
    return InlineKeyboardMarkup(buttons)
