import re
import math
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- REGEX PATTERNS ---
LANG_PATTERNS = {
    "Hindi": re.compile(r'\b(hindi|hin|dub|dual)\b', re.IGNORECASE),
    "English": re.compile(r'\b(english|eng)\b', re.IGNORECASE),
    "Tamil": re.compile(r'\b(tamil|tam)\b', re.IGNORECASE),
    "Telugu": re.compile(r'\b(telugu|tel)\b', re.IGNORECASE),
    "Malayalam": re.compile(r'\b(malayalam|mal)\b', re.IGNORECASE), # Added Malayalam
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
# 🛠️ BUTTON PARSER
# ==========================================
async def btn_parser(search_id, files, client, offset, a_type=None, a_lang=None, a_qual=None, a_year=None, a_size=None, a_sort=None, years=None):
    buttons = []
    
    def s(val): return val if val else "None"
    
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
    
    if any([a_type, a_lang, a_qual, a_year, a_size, a_sort]):
         type_row.append(InlineKeyboardButton("🔄 Reset", callback_data=f"{base}_None_None_None_None_None_None"))
    buttons.append(type_row)

    # 3. LANG & QUAL BUTTONS
    lq_row = []
    
    # 🌍 Select Language Button
    lang_label = f"{a_lang.title()} ✅" if a_lang and a_lang != "None" else "🌍 Select Language"
    lq_row.append(InlineKeyboardButton(lang_label, callback_data=f"langmenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    
    # 📺 Select Quality Button
    qual_label = f"{a_qual} ✅" if a_qual and a_qual != "None" else "📺 Select Quality"
    lq_row.append(InlineKeyboardButton(qual_label, callback_data=f"qualmenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    
    buttons.append(lq_row)

    # 4. YEAR & SIZE BUTTONS
    ys_row = []
    
    # 📅 Select Year Button
    year_label = f"{a_year} ✅" if a_year and a_year != "None" else "📅 Select Year"
    ys_row.append(InlineKeyboardButton(year_label, callback_data=f"yearmenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))

    # 💾 Select Size Button
    size_labels = {"s": "<500MB", "m": "500MB-1GB", "l": "1GB-2GB", "xl": ">2GB"}
    size_display = size_labels.get(a_size, a_size)
    size_label = f"{size_display} ✅" if a_size and a_size != "None" else "💾 Select Size"
    ys_row.append(InlineKeyboardButton(size_label, callback_data=f"sizemenu_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"))
    
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
# 🌍 LANGUAGE MENU GENERATOR
# ==========================================
async def lang_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
    def s(val): return val if val else "None"
    
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    buttons = []
    options = [
        ("hindi", "Hindi"),
        ("english", "English"), 
        ("tamil", "Tamil"), 
        ("telugu", "Telugu"),
        ("malayalam", "Malayalam") # Added Malayalam
    ]
    
    row = []
    for code, label in options:
        is_active = (code == a_lang)
        text = f"{label} ✅" if is_active else label
        val = "None" if is_active else code
        # Notice we pass `val` as the selected language for the callback
        base_data = f"filter_{search_id}_0_{s(a_type)}_{val}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        row.append(InlineKeyboardButton(text, callback_data=base_data))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: buttons.append(row)

    if a_lang and a_lang != "None":
        all_lang_data = f"filter_{search_id}_0_{s(a_type)}_None_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        buttons.append([InlineKeyboardButton("🌍 All Languages", callback_data=all_lang_data)])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)

# ==========================================
# 🆕 SORT MENU GENERATOR
# ==========================================
async def sort_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
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
# 📺 QUALITY MENU GENERATOR
# ==========================================
async def qual_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
    def s(val): return val if val else "None"
    
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    buttons = []
    options = [("1080p", "1080p"), ("720p", "720p"), ("480p", "480p"), ("hd", "HD"), ("4k", "4k")]
    
    row = []
    for code, label in options:
        is_active = (code == a_qual)
        text = f"{label} ✅" if is_active else label
        val = "None" if is_active else code
        base_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{val}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        row.append(InlineKeyboardButton(text, callback_data=base_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    if a_qual and a_qual != "None":
        all_qual_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_None_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
        buttons.append([InlineKeyboardButton("🌌 All Qualities", callback_data=all_qual_data)])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)

# ==========================================
# 📅 YEAR MENU GENERATOR
# ==========================================
async def year_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort, available_years):
    def s(val): return val if val else "None"
    
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    buttons = []
    if not available_years:
        available_years = ["2025", "2024", "2023", "2022", "2021", "2020"]
        
    years_to_show = available_years[:8]
    
    row = []
    for year in years_to_show:
        yr_str = str(year)
        is_active = (yr_str == str(a_year))
        text = f"{yr_str} ✅" if is_active else yr_str
        
        val = "None" if is_active else yr_str
        base_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{val}_{s(a_size)}_{s(a_sort)}"
        
        row.append(InlineKeyboardButton(text, callback_data=base_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: buttons.append(row)

    if a_year and a_year != "None":
        all_year_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_None_{s(a_size)}_{s(a_sort)}"
        buttons.append([InlineKeyboardButton("📅 All Years", callback_data=all_year_data)])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)

# ==========================================
# 💾 SIZE MENU GENERATOR
# ==========================================
async def size_menu_buttons(search_id, offset, a_type, a_lang, a_qual, a_year, a_size, a_sort):
    def s(val): return val if val else "None"
    
    back_data = f"filter_{search_id}_{offset}_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{s(a_size)}_{s(a_sort)}"
    
    buttons = []
    options = [
        ("s", "<500MB"), 
        ("m", "500MB - 1GB"), 
        ("l", "1GB - 2GB"), 
        ("xl", ">2GB")
    ]
    
    row = []
    for code, label in options:
        is_active = (code == a_size)
        text = f"{label} ✅" if is_active else label
        
        val = "None" if is_active else code
        base_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_{val}_{s(a_sort)}"
        
        row.append(InlineKeyboardButton(text, callback_data=base_data))
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row: buttons.append(row)

    if a_size and a_size != "None":
        all_size_data = f"filter_{search_id}_0_{s(a_type)}_{s(a_lang)}_{s(a_qual)}_{s(a_year)}_None_{s(a_sort)}"
        buttons.append([InlineKeyboardButton("💾 All Sizes", callback_data=all_size_data)])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=back_data)])
    return InlineKeyboardMarkup(buttons)
