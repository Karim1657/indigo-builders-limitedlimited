import telebot
from telebot import types
from datetime import datetime, timedelta
import re
import random
import json
import os
import time
import threading
import requests
import uuid
import secrets
import hashlib
import base64
import hmac
from werkzeug.security import generate_password_hash, check_password_hash


# ---- .env loader (works with or without python-dotenv) ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        with open(_env_path, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ================= CONFIGURATION =================
# Termux note: this version uses Python standard-library crypto for CVC storage;
# no 'cryptography' package is required.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")               # Token from BotFather
BOT_USERNAME = os.environ.get("BOT_USERNAME", "indigo0_bot")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7004073782"))                          # Admin Telegram ID
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@MATICWAVE100")                    # Official Telegram Channel
COMPANY_NAME = "INDIGO BUILDERS LIMITED"
USDT_ADDRESS = os.environ.get("USDT_ADDRESS", "TRC20_YOUR_USDT_WALLET_ADDRESS") # USDT TRC20 Wallet Address
MIN_DEPOSIT = 10.0                              # Minimum Deposit (USDT)
MIN_WITHDRAW = 5.0                              # Minimum Withdraw (USDT)

# --- TRC20 SMART CONTRACT CONFIGURATION ---
TRC20_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

DB_FILE = os.environ.get("DB_FILE", "bot_database.json")                   # Database File
SESSION_TIMEOUT_SECONDS = 1200                  # 20 Minutes Auto-Logout Limit
# =================================================

bot = telebot.TeleBot(BOT_TOKEN)

# Databases (In-Memory & JSON Persistent)
users = {}
used_txids = set()
pending_deposits = {}
pending_withdrawals = {}
pending_investment_confirmations = {}
pending_withdrawal_confirmations = {}
payment_methods = {}   # Admin-managed deposit payment methods (see PAYMENT METHODS section)

# --- DATABASE PERSISTENCE FUNCTIONS ---
def load_data():
    global users, used_txids, pending_deposits, pending_withdrawals, pending_investment_confirmations, pending_withdrawal_confirmations, payment_methods
    payment_methods = {}
    users = {}
    used_txids = set()
    pending_deposits = {}
    pending_withdrawals = {}
    pending_investment_confirmations = {}
    pending_withdrawal_confirmations = {}
    if not os.path.exists(DB_FILE):
        return
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        users = {int(k): v for k, v in data.get('users', {}).items()}
        used_txids = set(data.get('used_txids', []))
        pending_deposits = data.get('pending_deposits', {})
        pending_withdrawals = data.get('pending_withdrawals', {})
        pending_investment_confirmations = data.get('pending_investment_confirmations', {})
        pending_withdrawal_confirmations = data.get('pending_withdrawal_confirmations', {})
        payment_methods = data.get('payment_methods', {})
        print("Database loaded successfully.")
    except Exception as e:
        print(f"Error loading database: {e}")

def save_data():
    try:
        data = {
            'users': users,
            'used_txids': list(used_txids),
            'pending_deposits': pending_deposits,
            'pending_withdrawals': pending_withdrawals,
            'pending_investment_confirmations': pending_investment_confirmations,
            'pending_withdrawal_confirmations': pending_withdrawal_confirmations,
            'payment_methods': payment_methods
        }
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ Error saving database: {e}")

# --- HELPER FUNCTIONS ---
def mask_id(user_id):
    s = str(user_id)
    if len(s) <= 4:
        return s
    return s[:3] + "****" + s[-3:]

def mask_wallet(wallet):
    if not wallet or wallet == 'Not Set' or len(wallet) <= 8:
        return wallet
    return wallet[:4] + "******" + wallet[-4:]

def mask_txid(txid):
    if not txid or len(txid) < 8:
        return txid
    return txid[:4] + "******" + txid[-4:]

def is_valid_txid(txid):
    txid = (txid or "").strip()
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", txid))

def is_valid_trc20(wallet):
    if not wallet or len(wallet) != 34 or not wallet.startswith('T'):
        return False
    pattern = r'^T[1-9A-HJ-NP-Za-km-z]{33}$'
    return bool(re.match(pattern, wallet))

def get_current_time():
    return datetime.now().strftime("%d-%m-%Y | %I:%M:%S %p")

def get_current_date_only():
    return datetime.now().strftime("%d-%m-%Y")


# ================= SECURITY HARDENING =================
def hash_password_secure(password):
    """Strong one-way password hash. Never store plaintext passwords."""
    return generate_password_hash(password, method="scrypt")

def verify_password_secure(stored_password, candidate_password):
    """
    Verify a password hash. Legacy plaintext is accepted only for migration;
    callers should re-hash it immediately after successful login.
    """
    if not stored_password:
        return False
    try:
        if stored_password.startswith(("scrypt:", "pbkdf2:", "argon2:")):
            return check_password_hash(stored_password, candidate_password)
    except Exception:
        return False
    return stored_password == candidate_password

def make_unique_tx_id(prefix="TX"):
    return f"{prefix}{uuid.uuid4().hex[:20].upper()}"


# ================= TEMP MESSAGE / CURRENCY HELPERS =================
def send_temp_message(chat_id, text, reply_markup=None, parse_mode="Markdown", delay=45):
    """Send a normal user handler message and remove it automatically."""
    try:
        msg = bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        def _delete():
            try:
                bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
        timer = threading.Timer(delay, _delete)
        timer.daemon = True
        timer.start()
        return msg
    except Exception:
        return None

CURRENCY_CODES = {
    'USDT':'Tether USD (TRC20)', 'USD':'US Dollar', 'EUR':'Euro', 'INR':'Indian Rupee', 'BDT':'Bangladeshi Taka',
    'SAR':'Saudi Riyal', 'BHD':'Bahraini Dinar', 'AED':'UAE Dirham', 'GBP':'British Pound',
    'CAD':'Canadian Dollar', 'AUD':'Australian Dollar', 'SGD':'Singapore Dollar',
    'MYR':'Malaysian Ringgit', 'PKR':'Pakistani Rupee', 'JPY':'Japanese Yen',
    'CNY':'Chinese Yuan', 'KRW':'South Korean Won', 'TRY':'Turkish Lira',
    'RUB':'Russian Ruble', 'CHF':'Swiss Franc', 'NZD':'New Zealand Dollar',
    'ZAR':'South African Rand', 'NOK':'Norwegian Krone', 'SEK':'Swedish Krona',
    'DKK':'Danish Krone', 'THB':'Thai Baht', 'IDR':'Indonesian Rupiah'
}
_exchange_cache = {'timestamp': 0, 'rates': {}}


# ================= ENGLISH-ONLY UI / FAST MODE =================
# The bot intentionally runs in the original English UI. The language selector
# is removed from Account Settings, and no online translation requests are made.
LANGUAGE_UI = {
    'English': {
        'language_saved':'Language preference saved.',
        'dashboard':'👤 My Dashboard', 'investments':'📈 Investment Plans',
        'history':'📜 Transaction History', 'deposit':'📥 Deposit Funds',
        'withdraw':'📤 Withdraw Funds', 'card':'💳 Virtual Card',
        'referral':'🎁 Referral Program', 'settings':'⚙️ Account Settings',
        'about':'ℹ️ About Us', 'support':'🎧 Support', 'logout':'🚪 Logout Account',
        'admin':'👑 Admin Panel', 'total_fee':'TOTAL FEE',
        'current_pin':'Enter your current 4-digit card PIN:',
        'new_pin':'Enter a new 4-digit card PIN:',
        'pin_verified':'Previous PIN verified. Enter your new 4-digit card PIN:',
        'pin_changed':'Card PIN changed successfully.',
        'pin_failed':'Previous PIN verification failed. PIN was not changed.',
        'frozen_withdraw':'Your card is frozen. Withdrawals are disabled until the administrator unfreezes the card.'
    }
}
LANGUAGE_CODES = {'English':'en'}

def _user_language(user_id):
    return 'English'

def translate_text(text, target_language='English'):
    return text

def _localize_markup(markup, target_language='English'):
    return markup

def tr(user_id, key, fallback=None):
    return LANGUAGE_UI['English'].get(key, fallback or key)

def localized_action_texts(action_key):
    return [LANGUAGE_UI['English'].get(action_key, action_key)]

def force_reply_markup(user_id=None):
    # Automatic ForceReply keyboard is intentionally disabled for faster and
    # cleaner input handling. Telegram will use the normal message composer.
    return None

def get_currency_rate(code):
    code = str(code or 'USDT').upper()
    if code in ('USD', 'USDT'):
        return 1.0
    now = time.time()
    if now - _exchange_cache['timestamp'] > 900:
        try:
            r = requests.get('https://open.er-api.com/v6/latest/USD', timeout=8)
            payload = r.json()
            rates = payload.get('rates', {})
            if rates:
                _exchange_cache['rates'] = rates
                _exchange_cache['timestamp'] = now
        except Exception as e:
            print(f'Currency rate lookup failed: {e}')
    return float(_exchange_cache['rates'].get(code, 1.0))

def format_user_balance(amount, currency='USDT'):
    currency = str(currency or 'USDT').upper()
    rate = get_currency_rate(currency)
    value = float(amount or 0.0) * rate
    return f"{value:,.2f} {currency}"

def get_trx_price_usd():
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/simple/price',
            params={'ids':'tron', 'vs_currencies':'usd'}, timeout=8
        )
        price = float(r.json().get('tron', {}).get('usd', 0))
        if price > 0:
            return price
    except Exception as e:
        print(f'TRX price lookup failed: {e}')
    return None

TRX_WITHDRAWAL_FEE = 1.5

def withdrawal_fee_summary(amount):
    price = get_trx_price_usd()
    if not price:
        return None
    fee_usd = round(TRX_WITHDRAWAL_FEE * price, 6)
    net = round(float(amount) - fee_usd, 6)
    return {'fee_trx': TRX_WITHDRAWAL_FEE, 'trx_price': price, 'fee_usd': fee_usd, 'net_amount': net}

def notification_enabled(user_id, event_type):
    data = get_user_data(user_id)
    settings = data.get('notification_settings', {})
    return bool(settings.get(str(event_type).lower(), True))

def anti_phishing_suffix(user_id):
    code = get_user_data(user_id).get('anti_phishing_code', '')
    return f"\n🛡️ *Anti-Phishing Code:* `{code}`" if code else ''

# ================= VIRTUAL WITHDRAWAL CARD =================
# Internal virtual card only. It is NOT a Mastercard-issued payment card.
def _hash_card_secret(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _card_crypto_key():
    # Standard-library-only key derivation from the bot token.
    # The bot token must remain secret.
    return hashlib.sha256(
        (BOT_TOKEN + "|BD_P2P_CARD_CVC_V1").encode("utf-8")
    ).digest()

def _card_keystream(key, nonce, length):
    blocks = []
    counter = 0
    total = 0
    while total < length:
        block = hmac.new(
            key,
            b"BD_P2P_CARD_STREAM|" + nonce + counter.to_bytes(8, "big"),
            hashlib.sha256
        ).digest()
        blocks.append(block)
        total += len(block)
        counter += 1
    return b"".join(blocks)[:length]

def _encrypt_card_cvc(cvc):
    # Authenticated, reversible CVC storage without third-party packages.
    # Format: v1.<base64(nonce + ciphertext + tag)>
    key = _card_crypto_key()
    plaintext = str(cvc).encode("utf-8")
    nonce = secrets.token_bytes(16)
    stream = _card_keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(
        key, b"BD_P2P_CARD_TAG|" + nonce + ciphertext, hashlib.sha256
    ).digest()[:16]
    return "v1." + base64.urlsafe_b64encode(
        nonce + ciphertext + tag
    ).decode("ascii")

def _decrypt_card_cvc(token):
    if not token or not str(token).startswith("v1."):
        return None
    try:
        raw = base64.urlsafe_b64decode(str(token)[3:].encode("ascii"))
        if len(raw) < 32:
            return None
        nonce = raw[:16]
        tag = raw[-16:]
        ciphertext = raw[16:-16]
        key = _card_crypto_key()
        expected = hmac.new(
            key, b"BD_P2P_CARD_TAG|" + nonce + ciphertext, hashlib.sha256
        ).digest()[:16]
        if not hmac.compare_digest(tag, expected):
            return None
        stream = _card_keystream(key, nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream))
        return plaintext.decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError):
        return None

def send_card_temp_message(chat_id, text, reply_markup=None, parse_mode="Markdown", delay=20):
    """Send a card UI message and automatically delete it after delay seconds."""
    try:
        msg = bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        def _delete():
            try:
                bot.delete_message(chat_id, msg.message_id)
            except Exception:
                pass
        timer = threading.Timer(delay, _delete)
        timer.daemon = True
        timer.start()
        return msg
    except Exception:
        return None

def delete_user_secret_message(message):
    """Immediately remove a user's PIN/password/other secret input from Telegram chat."""
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

def _mask_card_number(number):
    s = str(number or "")
    return ("•" * max(0, len(s) - 4)) + s[-4:] if s else "Not issued"

def _card_defaults(data):
    data.setdefault("virtual_card", {
        "status": "NOT_ISSUED", "number": "", "cvc_hash": "",
        "expiry": "", "cvc_encrypted": "", "pin_hash": "", "pin_set": False,
        "created_at": "", "last_pin_change": "",
        "failed_reveals": 0, "locked": False, "freeze_reason": "", "admin_frozen": False, "daily_limit": 500.0, "daily_used": 0.0
    })
    card = data["virtual_card"]
    card.setdefault("admin_frozen", card.get("status") == "FROZEN")
    if card.get("status") == "FROZEN":
        card["admin_frozen"] = True
    return card

def issue_virtual_card(user_id):
    data = get_user_data(user_id)
    card = _card_defaults(data)
    # An administrator freeze is absolute. Never issue/reissue a card while
    # an admin freeze is active; doing so could accidentally restore ACTIVE.
    if card.get("admin_frozen") or card.get("status") == "FROZEN":
        return card, None
    if card.get("status") == "ACTIVE" and card.get("number"):
        return card, None
    card["number"] = "9" + "".join(str(secrets.randbelow(10)) for _ in range(15))
    cvc = "".join(str(secrets.randbelow(10)) for _ in range(3))
    card["cvc_hash"] = _hash_card_secret(cvc)
    card["cvc_encrypted"] = _encrypt_card_cvc(cvc)
    card["expiry"] = (datetime.now() + timedelta(days=365*3)).strftime("%m/%y")
    card["status"] = "ACTIVE"
    card["created_at"] = get_current_time()
    card["pin_set"] = False
    card["pin_hash"] = ""
    card["failed_reveals"] = 0
    card["locked"] = False
    save_data()
    return card, cvc

def set_virtual_card_pin(user_id, pin, admin_override=False):
    data = get_user_data(user_id)
    card = _card_defaults(data)
    # Administrator freeze is a hard lock. User PIN changes are NEVER
    # permitted while admin_frozen is set, regardless of stale handlers,
    # button state, or the card status value. Only explicit admin override
    # may set/reset a PIN on a frozen card.
    if card.get("admin_frozen") and not admin_override:
        return False
    if card.get("status") != "ACTIVE" and not (admin_override and card.get("status") == "FROZEN"):
        return False
    if not re.fullmatch(r"\d{4}", str(pin or "")):
        return False
    card["pin_hash"] = _hash_card_secret(pin)
    card["pin_set"] = True
    card["last_pin_change"] = get_current_time()
    save_data()
    return True

def admin_adjust_balance(target_id, amount, reason):
    data = get_user_data(target_id)
    amount = float(amount)
    if amount == 0 or data.get("balance", 0.0) + amount < 0:
        return False
    data["balance"] += amount
    add_transaction(
        target_id, "Admin Balance Adjustment", abs(amount), "Completed",
        f"{'Credit' if amount > 0 else 'Debit'}: {reason}"
    )
    save_data()
    return True

def get_user_data(user_id, username=None):
    user_id = int(user_id)
    if user_id not in users:
        users[user_id] = {
            'registered': False,
            'logged_in': False,
            'banned': False,
            'last_login_time': 0,
            'username': username or 'N/A',
            'password': 'Not Set',
            'balance': 0.0,
            'total_deposited': 0.0,
            'total_withdrawn': 0.0,
            'total_fees': 0.0,
            'total_invested': 0.0,
        'total_profit': 0.0,
            'last_investment_timestamp': 0,
            'wallet': 'Not Set',
            'active_plans': [],
            'transactions': [],
            'referred_by': None,
            'referrals_count': 0,
            'referral_earnings': 0.0,
            'withdrawal_timestamps': [],
            'failed_login_attempts': 0,
            'withdrawal_permissions': 0,
            'wallet_gateway': 'USDT TRC20',
            'default_currency': 'USDT',
            'notification_settings': {
                'deposit': True, 'withdrawal': True, 'referral': True, 'investment': True, 'security': True
            },
            'language': 'English',
            'anti_phishing_code': '',
            'auto_reinvest': False,
            'active_bot_sessions': []
        }
        save_data()
    elif username and users[user_id].get('username') != username:
        users[user_id]['username'] = username
        save_data()
    
    if 'withdrawal_timestamps' not in users[user_id]:
        users[user_id]['withdrawal_timestamps'] = []
    if 'failed_login_attempts' not in users[user_id]:
        users[user_id]['failed_login_attempts'] = 0
    if 'withdrawal_permissions' not in users[user_id]:
        users[user_id]['withdrawal_permissions'] = 0
    users[user_id].setdefault('total_fees', 0.0)
    users[user_id].setdefault('total_profit', 0.0)
    if not users[user_id].get('total_profit_backfilled'):
        # One-time: rebuild lifetime profit for accounts created before this field was tracked.
        _bf = 0.0
        for _tx in users[user_id].get('transactions', []):
            try:
                _t = _tx.get('type', '')
                _d = _tx.get('details', '') or ''
                if _t == 'Investment Maturity':
                    _m = re.search(r'Profit: \+\$([0-9.]+)', _d)
                    if _m:
                        _bf += float(_m.group(1))
                elif _t == 'Auto-Reinvest':
                    _rate = 0.07 if ('Pro' in _d or 'VIP' in _d) else 0.05
                    _tot = float(_tx.get('amount', 0.0) or 0.0)
                    _bf += _tot - (_tot / (1 + _rate))
            except Exception:
                pass
        users[user_id]['total_profit'] = round(float(users[user_id].get('total_profit', 0.0) or 0.0) + _bf, 2)
        users[user_id]['total_profit_backfilled'] = True
    users[user_id].setdefault('wallet_gateway', 'USDT TRC20')
    users[user_id].setdefault('default_currency', 'USDT')
    users[user_id].setdefault('notification_settings', {'deposit': True, 'withdrawal': True, 'referral': True, 'investment': True, 'security': True})
    users[user_id]['language'] = 'English'
    users[user_id].setdefault('anti_phishing_code', '')
    users[user_id].setdefault('auto_reinvest', False)
    users[user_id].setdefault('active_bot_sessions', [])
    if 'banned' not in users[user_id]:
        users[user_id]['banned'] = False
        
    return users[user_id]

def search_users_by_query(query):
    query_str = str(query).strip().lower()
    clean_query = query_str.replace('@', '')
    results = []
    
    for uid, udata in users.items():
        uid_str = str(uid).lower()
        uname = udata.get('username', '').lower().replace('@', '')
        balance_str = f"{udata.get('balance', 0.0):.2f}"
        
        if (clean_query == uid_str or 
            clean_query == uname or 
            clean_query == balance_str):
            results.append((uid, udata))
            
    return results

def is_logged_in_valid(user_id):
    data = get_user_data(user_id)
    if not data.get('registered', False):
        return False
    if not data.get('logged_in', False):
        return False
    
    last_login = data.get('last_login_time', 0)
    if (time.time() - last_login) > SESSION_TIMEOUT_SECONDS:
        data['logged_in'] = False
        save_data()
        return False
    return True

def add_transaction(user_id, tx_type, amount, status, details=""):
    data = get_user_data(user_id)
    tx_id = make_unique_tx_id("TX")
    record = {
        'tx_id': tx_id,
        'type': tx_type,
        'amount': amount,
        'status': status,
        'date': get_current_time(),
        'timestamp': datetime.now().timestamp(),
        'details': details
    }
    data['transactions'].append(record)
    save_data()
    return record

# --- TRON BLOCKCHAIN AUTO VERIFIER ---
def verify_tron_usdt_onchain(txid, expected_amount):
    """
    Robust TRC20 USDT deposit verifier.
    Checks confirmed TRON transaction events and requires the transfer
    recipient to match the configured USDT deposit address.
    Returns (True, verified_amount) only when the on-chain transfer is valid.
    """
    txid = (txid or "").strip()
    try:
        if not is_valid_txid(txid):
            return False, 0.0

        if not USDT_ADDRESS or USDT_ADDRESS.startswith("TRC20_YOUR_"):
            print("Deposit verifier error: USDT_ADDRESS is still a placeholder.")
            return False, 0.0

        headers = {"accept": "application/json"}
        base = "https://api.trongrid.io"
        endpoints = [
            f"{base}/v1/transactions/{txid}/events?only_confirmed=true&limit=200",
            f"{base}/v1/transactions/{txid}/events?limit=200",
        ]

        last_status = None
        for url in endpoints:
            try:
                res = requests.get(url, headers=headers, timeout=(5, 12))
                last_status = res.status_code
                if res.status_code != 200:
                    continue

                payload = res.json() if res.content else {}
                events = payload.get("data") or []

                for ev in events:
                    if ev.get("event_name") != "Transfer":
                        continue
                    if ev.get("contract_address") != TRC20_USDT_CONTRACT:
                        continue

                    result = ev.get("result") or {}
                    # TronGrid event result keys can be named or indexed.
                    raw_value = result.get("value")
                    if raw_value is None:
                        raw_value = result.get("2")
                    if raw_value is None:
                        continue

                    try:
                        amount_usdt = int(raw_value) / 1_000_000.0
                    except (TypeError, ValueError):
                        continue

                    # Prefer named/indexed recipient fields.
                    recipient = (
                        result.get("to")
                        or result.get("_to")
                        or result.get("1")
                        or result.get("to_address")
                        or ""
                    )

                    # Some TronGrid responses may omit decoded recipient in the
                    # event result; fall back to transaction info's contract data.
                    recipient_ok = recipient == USDT_ADDRESS

                    if not recipient_ok:
                        try:
                            info = requests.get(
                                f"{base}/wallet/gettransactioninfobyid",
                                params={"value": txid},
                                headers=headers,
                                timeout=(5, 8),
                            )
                            info_json = info.json() if info.content else {}
                            contract_result = (
                                info_json.get("contractResult")
                                or info_json.get("contract_result")
                                or ""
                            )
                            # The event itself is still the source of amount;
                            # when recipient cannot be decoded here, do not
                            # auto-credit. This avoids crediting an unrelated
                            # transfer.
                        except Exception:
                            pass

                    if not recipient_ok:
                        continue

                    # Require the amount to meet the requested deposit.
                    if amount_usdt + 1e-8 >= float(expected_amount):
                        return True, amount_usdt

                # A valid response with no matching event should not be treated
                # as a transient error; continue to the fallback endpoint.
            except requests.RequestException as e:
                print(f"TRON API request failed: {e}")
                continue
            except (ValueError, TypeError) as e:
                print(f"TRON API response parse failed: {e}")
                continue

        print(f"TRON deposit verification failed for TxID {txid[:8]}... status={last_status}")
        return False, 0.0

    except Exception as e:
        print(f"Blockchain auto check error: {e}")
        return False, 0.0

# --- CELEBRATION EMOJI EFFECT FUNCTION ---
def show_celebration_effect(chat_id):
    try:
        msg = bot.send_message(
            chat_id,
            "🥳🎉🎊✨ **PORTFOLIO TRANSACTION PROCESSED SUCCESSFULLY!** ✨🎊🎉🥳\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "      🎈 🥂 🍾 🎁 🎆 🌟 🎈\n"
            "  ✨ 🥳 CONGRATULATIONS! 🥳 ✨\n"
            "      🎈 🎆 🎁 🍾 🥂 🎈\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown"
        )
        time.sleep(5)
        bot.delete_message(chat_id, msg.message_id)
    except Exception as e:
        print(f"Celebration effect error: {e}")

# --- 15 MINUTES AUTO-REFUND BACKGROUND THREAD ---
def auto_refund_checker():
    while True:
        try:
            time.sleep(10)
            now_ts = datetime.now().timestamp()
            expired_ids = []

            for wd_id, req in list(pending_withdrawals.items()):
                req_ts = req.get('timestamp', now_ts)
                if (now_ts - req_ts) >= (15 * 60):
                    expired_ids.append((wd_id, req))

            for wd_id, req in expired_ids:
                if wd_id in pending_withdrawals:
                    pending_withdrawals.pop(wd_id, None)
                    u_id = req['user_id']
                    amt = req['amount']
                    admin_msg_id = req.get('admin_msg_id')
                    u_data = get_user_data(u_id)
                    
                    u_data['balance'] += amt
                    add_transaction(u_id, "Withdrawal", amt, "Cancelled (System Auto-Refund)", "Admin processing session timeout exceeded 15 minutes")
                    save_data()

                    if admin_msg_id:
                        try:
                            bot.delete_message(chat_id=ADMIN_ID, message_id=admin_msg_id)
                        except Exception as e:
                            print(f"Failed to delete admin message on timeout: {e}")

                    try:
                        bot.send_message(
                            u_id,
                            f"🙏 *SYSTEM PROCESSING NOTICE & APOLOGY!*\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"Dear Valued Investor,\n\n"
                            f"Your capital withdrawal request of **${amt:.2f}** could not be finalized within the designated operational window.\n\n"
                            f"💰 **AUTOMATIC BALANCE REVERSAL:** The full requested amount of **${amt:.2f}** has been securely reinstated to your active asset balance.\n\n"
                            f"✨ You may now execute a new payout request at your convenience. Thank you for your cooperation!",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print(f"Auto refund bot notification failed: {e}")

        except Exception as e:
            print(f"Auto-refund thread exception: {e}")

threading.Thread(target=auto_refund_checker, daemon=True).start()

# --- 24 HOUR COUNTDOWN CALCULATOR ---
def get_investment_countdown_by_timestamp(last_ts):
    if last_ts == 0:
        return "`00h 00m 00s (STANDBY)`"
    
    now_ts = datetime.now().timestamp()
    elapsed = now_ts - last_ts
    total_cycle_seconds = 24 * 3600
    
    if elapsed >= total_cycle_seconds:
        remaining = total_cycle_seconds - (elapsed % total_cycle_seconds)
    else:
        remaining = total_cycle_seconds - elapsed
        
    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    seconds = int(remaining % 60)
    
    return f"`{hours:02d}H {minutes:02d}M {seconds:02d}S`"

# --- 24 HOUR INVESTMENT MATURITY PROCESSOR ---
def get_plan_roi(plan):
    """Return the configured ROI for an investment plan."""
    plan_name = str(plan.get('plan', ''))
    if 'Starter' in plan_name:
        return 0.05
    if 'VIP Pro' in plan_name or 'Pro' in plan_name:
        return 0.07
    return float(plan.get('roi', 0.0) or 0.0)


def process_matured_investments():
    """Settle every investment whose individual 24-hour countdown has ended."""
    now_ts = datetime.now().timestamp()
    matured_events = []

    for user_id, data in list(users.items()):
        active_plans = data.get('active_plans', [])
        if not active_plans:
            continue

        remaining_plans = []
        changed = False

        for plan in active_plans:
            started_ts = float(plan.get('timestamp', 0) or 0)
            amount = float(plan.get('amount', 0.0) or 0.0)

            if started_ts <= 0 or (now_ts - started_ts) < (24 * 3600):
                remaining_plans.append(plan)
                continue

            roi = get_plan_roi(plan)
            profit = round(amount * roi, 2)
            total_credit = round(amount + profit, 2)
            data['total_profit'] = round(float(data.get('total_profit', 0.0) or 0.0) + profit, 2)
            plan_name = plan.get('plan', 'Investment Package')

            if data.get('auto_reinvest', False):
                data['total_invested'] = round(float(data.get('total_invested', 0.0)) + total_credit, 2)
                remaining_plans.append({
                    'plan': plan_name, 'amount': total_credit, 'date': get_current_time(),
                    'timestamp': now_ts, 'roi': roi, 'compounded_from': amount
                })
                add_transaction(user_id, "Auto-Reinvest", total_credit, "Compounded", f"Plan: {plan_name} | Capital + Profit: ${total_credit:.2f}")
            else:
                data['balance'] = round(float(data.get('balance', 0.0)) + total_credit, 2)
                add_transaction(
                    user_id, "Investment Maturity", total_credit, "Completed & Credited",
                    f"Plan: {plan_name} | Capital: ${amount:.2f} | Profit: +${profit:.2f}"
                )

            changed = True
            matured_events.append((user_id, data.copy(), plan_name, amount, profit, total_credit, bool(data.get('auto_reinvest', False))))

        if changed:
            data['active_plans'] = remaining_plans
            save_data()

    for user_id, snapshot, plan_name, amount, profit, total_credit, reinvested in matured_events:
        try:
            send_premium_telegram_notification(
                user_id,
                "Investment Maturity",
                "INVESTMENT MATURITY COMPLETED",
                amount_text=f"+${total_credit:.2f}",
                balance_text=f"${snapshot.get('balance', 0.0):.2f}",
                status="COMPOUNDED" if reinvested else "COMPLETED & CREDITED",
                details=(
                    f"📦 *PLAN:* `{plan_name}`\n"
                    f"💰 *CAPITAL:* `${amount:.2f}`\n"
                    f"📈 *PROFIT:* `+${profit:.2f}`\n"
                    f"💎 *SETTLED VALUE:* `${total_credit:.2f}`\n"
                    "⏱️ *24H COUNTDOWN:* `COMPLETED`\n"
                    + ("🔁 *AUTO-REINVEST:* `ENABLED`" if reinvested else "💵 *DESTINATION:* `MAIN BALANCE`")
                )
            )
        except Exception as e:
            print(f"Investment maturity notification error for {user_id}: {e}")

        try:
            post_channel_investment_maturity(
                user_id, plan_name, amount, profit, total_credit
            )
        except Exception as e:
            print(f"Investment maturity channel broadcast error for {user_id}: {e}")


def investment_maturity_checker():
    """Background worker: check for matured investments every 5 seconds."""
    while True:
        try:
            process_matured_investments()
        except Exception as e:
            print(f"Investment maturity checker exception: {e}")
        time.sleep(5)


# --- THICKER 100% LOADING ANIMATION ---
def show_100_percent_loading(chat_id, action_title="PROCESSING SECURE REQUEST"):
    try:
        msg = bot.send_message(chat_id, f"⏳ **{action_title}...**\n`[████░░░░░░░░░░░░░░░░] 20%`", parse_mode="Markdown")
        time.sleep(0.4)
        bot.edit_message_text(f"⏳ **{action_title}...**\n`[██████████░░░░░░░░░░] 50%`", chat_id, msg.message_id, parse_mode="Markdown")
        time.sleep(0.4)
        bot.edit_message_text(f"🔄 **VERIFYING ENCRYPTION & DATA...**\n`[████████████████░░░░] 80%`", chat_id, msg.message_id, parse_mode="Markdown")
        time.sleep(0.4)
        bot.edit_message_text(f"⚡ **TRANSACTION COMPLETED SUCCESSFULLY...**\n`[████████████████████] 100%`", chat_id, msg.message_id, parse_mode="Markdown")
        time.sleep(0.2)
        bot.delete_message(chat_id, msg.message_id)
    except Exception as e:
        print(f"Loading animation error: {e}")

# --- CHANNEL MEMBERSHIP CHECK ---
def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

def get_verification_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    channel_link = f"https://t.me/{CHANNEL_ID.replace('@', '')}" 
    btn_join = types.InlineKeyboardButton("📢 Join Official Telegram Channel", url=channel_link)
    btn_verify = types.InlineKeyboardButton("🔄 Verify Channel Access", callback_data="check_verif")
    markup.add(btn_join, btn_verify)
    return markup

def registration_or_login_markup(is_registered=False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not is_registered:
        markup.add(types.InlineKeyboardButton("📝 Sign Up / Register Account", callback_data="start_registration"))
    else:
        markup.add(types.InlineKeyboardButton("🔑 Authenticate & Login", callback_data="start_login"))
    return markup

SUPPORT_URL = os.environ.get("SUPPORT_URL", "https://t.me/IBLtony")

def forgot_password_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔑 Forgot Password", callback_data="acc_forgot_pass"))
    return markup

def admin_panel_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔑 Change User Password", callback_data="adm_change_password"),
        types.InlineKeyboardButton("🚫 Terminate Active Investment & Refund", callback_data="adm_cancel_inv"),
        types.InlineKeyboardButton("🎟 Configure Withdrawal Allowances", callback_data="adm_set_wd_perm"),
        types.InlineKeyboardButton("🔨 User Ban & Unban Management", callback_data="adm_ban_manager"),
        types.InlineKeyboardButton("💳 Virtual Card PIN Management", callback_data="adm_card_pin"),
        types.InlineKeyboardButton("🔒 Freeze / Unfreeze Card", callback_data="adm_card_freeze"),
        types.InlineKeyboardButton("♻️ Replace User Card", callback_data="adm_card_replace"),
        types.InlineKeyboardButton("💰 User Balance + / -", callback_data="adm_balance"),
        types.InlineKeyboardButton("💱 Payment Methods (Add / ON-OFF)", callback_data="adm_pm"),
        types.InlineKeyboardButton("🗑 Delete User Account", callback_data="adm_delete_user")
    )
    return markup

# --- CHANNEL BROADCAST POSTS ---
def broadcast_to_channel(text):
    if CHANNEL_ID:
        try:
            bot.send_message(
                CHANNEL_ID,
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"Channel Broadcast Error: {e}")

def post_channel_deposit_success(user_id, amount, txid):
    msg = (
        "╔══════════════════════════════════════╗\n"
        "║      ✦ 𝐃𝐄𝐏𝐎𝐒𝐈𝐓 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄𝐃 ✦      ║\n"
        "╚══════════════════════════════════════╝\n\n"
        "💎 *OFFICIAL FUNDING UPDATE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Investor:* `{mask_id(user_id)}`\n"
        f"💰 *Amount Credited:* `+${amount:.2f}`\n"
        f"🔗 *Reference:* `{mask_txid(txid)}`\n"
        f"🟢 *Status:* `SUCCESSFULLY CREDITED`\n"
        f"🕒 *Time:* `{get_current_time()}`\n\n"
        "✨ *Your account funding has been recorded successfully.*\n"
        "Your available capital is now ready for the next step in your portfolio journey.\n\n"
        f"🏢 *{COMPANY_NAME}*\n"
        "_Secure • Transparent • Account-Focused_"
    )
    broadcast_to_channel(msg)

def post_channel_withdraw_success(user_id, amount, wallet):
    msg = (
        "╔══════════════════════════════════════╗\n"
        "║       ✦ 𝐖𝐈𝐓𝐇𝐃𝐑𝐀𝐖𝐀𝐋 𝐏𝐀𝐈𝐃 ✦       ║\n"
        "╚══════════════════════════════════════╝\n\n"
        "💸 *OFFICIAL PAYOUT UPDATE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Investor:* `{mask_id(user_id)}`\n"
        f"💵 *Amount Paid:* `-${amount:.2f}`\n"
        f"💳 *Destination:* `{mask_wallet(wallet)}`\n"
        f"🟢 *Status:* `PAYMENT SUCCESSFUL`\n"
        f"🕒 *Time:* `{get_current_time()}`\n\n"
        "✨ *Payout processing has been completed successfully.*\n"
        "Thank you for continuing to use our secure transaction channel.\n\n"
        f"🏢 *{COMPANY_NAME}*\n"
        "_Secure • Professional • Reliable_"
    )
    broadcast_to_channel(msg)

def post_channel_investment_maturity(user_id, plan_name, amount, profit, total_credit):
    msg = (
        "╔══════════════════════════════════════╗\n"
        "║      ✦ 𝐈𝐍𝐕𝐄𝐒𝐓𝐌𝐄𝐍𝐓 𝐌𝐀𝐓𝐔𝐑𝐄𝐃 ✦      ║\n"
        "╚══════════════════════════════════════╝\n\n"
        "🏆 *24-HOUR MATURITY CONFIRMATION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Investor:* `{mask_id(user_id)}`\n"
        f"📦 *Plan:* `{plan_name}`\n"
        f"💰 *Capital Returned:* `+${amount:.2f}`\n"
        f"📈 *Profit Credited:* `+${profit:.2f}`\n"
        f"💎 *Total Credited:* `+${total_credit:.2f}`\n"
        f"🟢 *Status:* `POSITION CLOSED & SETTLED`\n"
        f"🕒 *Time:* `{get_current_time()}`\n\n"
        "✨ *The 24-hour cycle has been completed successfully.*\n"
        "Capital and earned profit have been settled to the investor account.\n\n"
        f"🏢 *{COMPANY_NAME}*\n"
        "_Portfolio settlement completed automatically._"
    )
    broadcast_to_channel(msg)

def post_channel_transaction_cancelled(user_id, tx_type, amount, reason="Audit Failed"):
    msg = (
        "╔══════════════════════════════════════╗\n"
        "║      ✦ 𝐓𝐑𝐀𝐍𝐒𝐀𝐂𝐓𝐈𝐎𝐍 𝐑𝐄𝐕𝐄𝐑𝐓𝐄𝐃 ✦      ║\n"
        "╚══════════════════════════════════════╝\n\n"
        "⚠️ *OFFICIAL TRANSACTION NOTICE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Investor:* `{mask_id(user_id)}`\n"
        f"🏷 *Transaction:* `{tx_type}`\n"
        f"💰 *Amount:* `${amount:.2f}`\n"
        f"📝 *Reason:* `{reason}`\n"
        f"🔴 *Status:* `CANCELLED / REFUNDED`\n"
        f"🕒 *Time:* `{get_current_time()}`\n\n"
        "Your transaction status has been recorded in the account ledger.\n\n"
        f"🏢 *{COMPANY_NAME}*\n"
        "_Secure account notification_"
    )
    broadcast_to_channel(msg)

# --- KEYBOARDS ---
def deposit_quick_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("$10", callback_data="dep_quick_10"),
        types.InlineKeyboardButton("$20", callback_data="dep_quick_20"),
        types.InlineKeyboardButton("$30", callback_data="dep_quick_30"),
        types.InlineKeyboardButton("$50", callback_data="dep_quick_50"),
        types.InlineKeyboardButton("$100", callback_data="dep_quick_100"),
        types.InlineKeyboardButton("$500", callback_data="dep_quick_500")
    )
    markup.add(types.InlineKeyboardButton("✏️ Custom Capital Amount", callback_data="dep_quick_custom"))
    markup.add(types.InlineKeyboardButton("📜 Deposit History", callback_data="tx_history_deposit"))
    return markup

def withdraw_quick_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("$5", callback_data="wd_quick_5"),
        types.InlineKeyboardButton("$10", callback_data="wd_quick_10"),
        types.InlineKeyboardButton("$20", callback_data="wd_quick_20"),
        types.InlineKeyboardButton("$50", callback_data="wd_quick_50"),
        types.InlineKeyboardButton("$100", callback_data="wd_quick_100"),
        types.InlineKeyboardButton("$500", callback_data="wd_quick_500")
    )
    markup.add(types.InlineKeyboardButton("✏️ Custom Payout Amount", callback_data="wd_quick_custom"))
    markup.add(types.InlineKeyboardButton("📜 Withdrawal History", callback_data="tx_history_withdrawal"))
    return markup

def account_settings_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔒 Change Password", callback_data="acc_change_password"),
        types.InlineKeyboardButton("💳 Wallet / Address Settings", callback_data="acc_wallet_settings"),
        types.InlineKeyboardButton("💱 Default Currency", callback_data="acc_currency"),
        types.InlineKeyboardButton("🔔 Notification Settings", callback_data="acc_notifications"),
        types.InlineKeyboardButton("🛡️ Anti-Phishing Code", callback_data="acc_antiphishing"),
        types.InlineKeyboardButton("📱 Active Bot Session", callback_data="acc_sessions"),
        types.InlineKeyboardButton("📈 Auto-Reinvest / Compound", callback_data="acc_reinvest"),
        types.InlineKeyboardButton("🗑 Deactivate / Delete Account", callback_data="acc_delete_account")
    )
    return markup

def main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.row(types.KeyboardButton(tr(user_id, 'dashboard')))
    markup.row(types.KeyboardButton(tr(user_id, 'investments')), types.KeyboardButton(tr(user_id, 'history')))
    markup.row(types.KeyboardButton(tr(user_id, 'deposit')), types.KeyboardButton(tr(user_id, 'withdraw')))
    markup.add(types.KeyboardButton(tr(user_id, 'card')))
    markup.row(types.KeyboardButton(tr(user_id, 'referral')), types.KeyboardButton(tr(user_id, 'settings')))
    markup.add(types.KeyboardButton(tr(user_id, 'about')), types.KeyboardButton(tr(user_id, 'support')))
    markup.add(types.KeyboardButton(tr(user_id, 'logout')))
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton(tr(user_id, 'admin')))
    return markup

# --- START COMMAND & VERIFICATION ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    is_new = user_id not in users
    data = get_user_data(user_id, username=username)
    
    if data.get('banned', False):
        bot.send_message(message.chat.id, "🛑 **ACCESS RESTRICTED:** Your user profile has been suspended by administration.", parse_mode="Markdown")
        return

    args = message.text.split()
    if is_new and len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and referrer_id in users:
            data['referred_by'] = referrer_id
            ref_data = get_user_data(referrer_id)
            ref_data['referrals_count'] += 1
            save_data()

    if not is_subscribed(user_id):
        verif_text = (
            f"🛑 *CHANNEL ACCESS LOCKED!* 🛑\n\n"
            f"You MUST verify subscription to our official channel {CHANNEL_ID} to engage with this institutional bot."
        )
        bot.send_message(message.chat.id, verif_text, parse_mode="Markdown", reply_markup=get_verification_markup())
        return

    if not data['registered']:
        bot.send_message(
            message.chat.id,
            f"🏢 *Welcome to {COMPANY_NAME}!*\n\nPlease create your account Password to proceed.",
            parse_mode="Markdown",
            reply_markup=registration_or_login_markup(is_registered=False)
        )
    elif not is_logged_in_valid(user_id):
        bot.send_message(
            message.chat.id,
            f"🔑 *SESSION AUTHENTICATION REQUIRED*\n\nWelcome back! Please authenticate using your registered password:",
            parse_mode="Markdown",
            reply_markup=registration_or_login_markup(is_registered=True)
        )
    else:
        welcome_text = (
            f"🏢 *{COMPANY_NAME}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👋 *Welcome Back to Investor Terminal!*\n\n"
            "Choose a function from your dashboard menu below to manage your assets."
        )
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_keyboard(user_id))

@bot.callback_query_handler(func=lambda call: call.data == "check_verif")
def check_verif_callback(call):
    user_id = call.from_user.id
    username = call.from_user.username
    data = get_user_data(user_id, username=username)

    if data.get('banned', False):
        bot.answer_callback_query(call.id, "🛑 Account suspended.", show_alert=True)
        return

    if is_subscribed(user_id):
        bot.answer_callback_query(call.id, "✅ Channel Membership Verified Successfully!")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        
        if not data['registered']:
            bot.send_message(
                call.message.chat.id,
                "✅ *Subscription Verified!*\n\nPlease sign up to continue portfolio setup.",
                parse_mode="Markdown",
                reply_markup=registration_or_login_markup(is_registered=False)
            )
        elif not is_logged_in_valid(user_id):
            bot.send_message(
                call.message.chat.id,
                "✅ *Subscription Verified!*\n\nPlease log in to access secure dashboard.",
                parse_mode="Markdown",
                reply_markup=registration_or_login_markup(is_registered=True)
            )
        else:
            bot.send_message(call.message.chat.id, "✅ *Access Granted Successfully!*", parse_mode="Markdown", reply_markup=main_keyboard(user_id))
    else:
        bot.answer_callback_query(call.id, f"❌ Membership not found. Please join {CHANNEL_ID} first!", show_alert=True)

# --- SIGN UP / REGISTRATION FLOW ---
@bot.callback_query_handler(func=lambda call: call.data == "start_registration")
def start_registration_callback(call):
    user_id = call.from_user.id
    username = call.from_user.username
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    data = get_user_data(user_id, username=username)
    if data.get('banned', False):
        bot.send_message(call.message.chat.id, "🛑 Account suspended.")
        return

    if not is_subscribed(user_id):
        bot.send_message(call.message.chat.id, f"🛑 *Join {CHANNEL_ID} first!*", parse_mode="Markdown", reply_markup=get_verification_markup())
        return
    
    if data['registered']:
        bot.send_message(call.message.chat.id, "✅ *Account already registered! Please login.*", parse_mode="Markdown", reply_markup=registration_or_login_markup(True))
        return

    msg = bot.send_message(
        call.message.chat.id,
        "📝 *SECURE REGISTRATION*\n\n🔑 Please create your account **Password** (minimum 4 characters).\nYou will use this password every time you log in:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_reg_password)

def process_reg_password(message):
    user_id = message.from_user.id
    password = message.text.strip() if message.text else ""

    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

    if len(password) < 4:
        msg = bot.send_message(
            message.chat.id, 
            "❌ Password must comprise at least 4 alphanumeric characters.\nPlease submit your password:", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_reg_password)
        return

    show_100_percent_loading(message.chat.id, "FINALIZING ACCOUNT REGISTRATION")

    data = get_user_data(user_id, username=message.from_user.username)
    data['password'] = hash_password_secure(password)
    data['registered'] = True
    data['logged_in'] = True
    data['last_login_time'] = time.time()
    data['failed_login_attempts'] = 0
    save_data()

    bot.send_message(
        message.chat.id,
        f"🎉 *REGISTRATION COMPLETED SUCCESSFULLY!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 *PASSWORD:* `****`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome to **{COMPANY_NAME}**!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(user_id)
    )

# --- LOGIN FLOW ---
# Account password is for account login/recovery only. Card actions use Card PIN.
@bot.callback_query_handler(func=lambda call: call.data == "start_login")
def start_login_callback(call):
    user_id = call.from_user.id
    username = call.from_user.username
    bot.answer_callback_query(call.id)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    data = get_user_data(user_id, username=username)
    if data.get('banned', False):
        bot.send_message(call.message.chat.id, "🛑 Account suspended.")
        return

    if not data['registered']:
        bot.send_message(call.message.chat.id, "⚠️ No user credentials detected. Please Register first!", reply_markup=registration_or_login_markup(False))
        return

    msg = bot.send_message(
        call.message.chat.id, 
        f"🔑 *SECURE AUTHENTICATION LOGIN*\n\nPlease enter your account **Password** below:", 
        parse_mode="Markdown",
        reply_markup=forgot_password_markup()
    )
    bot.register_next_step_handler(msg, process_login_password)

def process_login_password(message):
    user_id = message.from_user.id
    pass_input = message.text.strip() if message.text else ""
    data = get_user_data(user_id, username=message.from_user.username)

    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

    password_ok = verify_password_secure(data.get('password', ''), pass_input)
    if password_ok:
        # Migrate any legacy plaintext password to a secure hash after successful login.
        stored_pw = data.get('password', '')
        if stored_pw == pass_input:
            data['password'] = hash_password_secure(pass_input)
    if not password_ok:
        data['failed_login_attempts'] = data.get('failed_login_attempts', 0) + 1
        save_data()

        if data['failed_login_attempts'] >= 3:
            bot.send_message(
                message.chat.id,
                "❌ **AUTHENTICATION ERROR (3 CONSECUTIVE FAILURES)!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "You have entered an incorrect password three times.\n\n"
                "Please tap **'Forgot Password'** below to contact Customer Service. The administrator will set a new password for you.",
                parse_mode="Markdown",
                reply_markup=forgot_password_markup()
            )
        else:
            attempts_left = 3 - data['failed_login_attempts']
            msg = bot.send_message(
                message.chat.id,
                f"❌ *Incorrect Password!*\nRemaining trials: **{attempts_left}**\n\nPlease enter your correct password:",
                parse_mode="Markdown",
                reply_markup=forgot_password_markup()
            )
            bot.register_next_step_handler(msg, process_login_password)
        return

    data['failed_login_attempts'] = 0
    show_100_percent_loading(message.chat.id, "AUTHENTICATING SESSION")
    data['logged_in'] = True
    data['last_login_time'] = time.time()
    save_data()

    bot.send_message(
        message.chat.id,
        f"🔓 *AUTHENTICATION SUCCESSFUL!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Welcome back to **{COMPANY_NAME}** Terminal!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(user_id)
    )

# --- ACCOUNT SETTINGS & FORGOT PASSWORD FLOW ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("acc_"))
def handle_account_settings_options(call):
    user_id = call.from_user.id
    data = get_user_data(user_id, username=call.from_user.username)
    bot.answer_callback_query(call.id)
    if data.get('banned', False):
        bot.answer_callback_query(call.id, "Account suspended.", show_alert=True)
        return

    if call.data == "acc_forgot_pass":
        try:
            bot.clear_step_handler_by_chat_id(call.message.chat.id)
        except Exception:
            pass
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("💬 Connect with Customer Service", url=SUPPORT_URL))
        markup.add(types.InlineKeyboardButton("⬅️ Back to Login", callback_data="acc_back_login"))
        bot.send_message(
            call.message.chat.id,
            "🎧 *CUSTOMER SERVICE – PASSWORD RESET*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Forgot your password? Please contact our Customer Service. "
            "The administrator will verify you and set a new password for your account.\n\n"
            "Tap the button below to connect now.",
            parse_mode="Markdown",
            reply_markup=markup
        )
    elif call.data == "acc_change_password":
        msg = send_temp_message(call.message.chat.id, "🔐 Enter your current account password:")
        bot.register_next_step_handler(msg, account_change_password_current)
    elif call.data == "acc_wallet_settings":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("USDT TRC20 — Update Address", callback_data="acc_set_wallet"))
        # Admin-added payment methods: let the user save their own account number for each ON method.
        custom_methods = [(mid, m) for mid, m in enabled_payment_methods() if mid != DEFAULT_METHOD_ID]
        saved_accounts = data.get('payment_accounts', {})
        for mid, m in custom_methods:
            has = bool(saved_accounts.get(mid, {}).get('account'))
            markup.add(types.InlineKeyboardButton(
                f"{m['name']} — {'Update' if has else 'Set'} Account Number",
                callback_data=f"acc_pm_set_{mid}"))
        markup.add(types.InlineKeyboardButton("⬅️ Back to Account Settings", callback_data="acc_settings_back"))
        if custom_methods:
            wallet_text = "💳 *WALLET / ADDRESS SETTINGS*\n\nSupported withdrawal gateway: `USDT TRC20`\n\n📱 *YOUR PAYMENT ACCOUNTS*\n"
            for mid, m in custom_methods:
                acc = str(saved_accounts.get(mid, {}).get('account', '')).replace("`", "")
                wallet_text += f"• {pm_escape(m['name'])}: " + (f"`{acc}`" if acc else "_Not set_") + "\n"
            wallet_text += "\nTap a method below to set or update your account number."
        else:
            wallet_text = "💳 *WALLET / ADDRESS SETTINGS*\n\nSupported withdrawal gateway: `USDT TRC20`\nBangladesh local payment methods are not supported."
        send_temp_message(call.message.chat.id, wallet_text, reply_markup=markup)
    elif call.data.startswith("acc_pm_set_"):
        mid = call.data[len("acc_pm_set_"):]
        m = get_payment_methods().get(mid)
        if not m or m.get("builtin") or not m.get("enabled", True):
            send_temp_message(call.message.chat.id, "❌ This payment method is currently unavailable.")
        else:
            msg = send_temp_message(
                call.message.chat.id,
                f"📱 Enter your *{pm_escape(m['name'])}* account number / address:\n_(Send /cancel to abort)_",
                delay=120)
            bot.register_next_step_handler(msg, save_user_payment_account, mid)
    elif call.data == "acc_set_wallet":
        msg = send_temp_message(call.message.chat.id, "💳 Enter your USDT TRC20 wallet address:")
        bot.register_next_step_handler(msg, save_trc20_wallet)
    elif call.data == "acc_currency":
        markup = types.InlineKeyboardMarkup(row_width=3)
        for code, name in CURRENCY_CODES.items():
            markup.add(types.InlineKeyboardButton(code, callback_data=f"acc_cur_{code}"))
        send_temp_message(call.message.chat.id, "💱 *DEFAULT CURRENCY*\n\nSelect the currency used to display your account balance. Ledger transactions remain denominated in USD.", reply_markup=markup)
    elif call.data.startswith("acc_cur_"):
        code = call.data.replace("acc_cur_", "").upper()
        if code in CURRENCY_CODES:
            data['default_currency'] = code
            save_data()
            send_temp_message(call.message.chat.id, f"✅ Default currency set to `{code}` — {CURRENCY_CODES[code]}.")
    elif call.data == "acc_notifications":
        ns = data.setdefault('notification_settings', {'deposit':True,'withdrawal':True,'referral':True,'investment':True,'security':True})
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, label in [('deposit','Deposit confirmations'),('withdrawal','Withdrawal updates'),('referral','Referral bonuses'),('investment','Investment updates'),('security','Security notifications')]:
            state = 'ON' if ns.get(key, True) else 'OFF'
            markup.add(types.InlineKeyboardButton(f"{label}: {state}", callback_data=f"acc_ntf_{key}"))
        send_temp_message(call.message.chat.id, "🔔 *NOTIFICATION SETTINGS*\n\nTap a setting to toggle Telegram notifications.", reply_markup=markup)
    elif call.data.startswith("acc_ntf_"):
        key = call.data.replace("acc_ntf_", "")
        ns = data.setdefault('notification_settings', {})
        ns[key] = not bool(ns.get(key, True))
        save_data()
        send_temp_message(call.message.chat.id, f"🔔 `{key.title()}` notifications are now {'ON' if ns[key] else 'OFF'}.")
    elif call.data == "acc_antiphishing":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➕ Set / Change Code", callback_data="acc_antiphishing_set"))
        markup.add(types.InlineKeyboardButton("🗑 Remove Code", callback_data="acc_antiphishing_remove"))
        current = data.get('anti_phishing_code') or 'Not set'
        send_temp_message(call.message.chat.id, f"🛡️ *ANTI-PHISHING CODE*\n\nCurrent status: `{current}`\n\nA code you recognize will appear in official security notifications.", reply_markup=markup)
    elif call.data == "acc_antiphishing_set":
        msg = send_temp_message(call.message.chat.id, "🛡️ Enter a private anti-phishing code (3–20 characters):")
        bot.register_next_step_handler(msg, save_antiphishing_code)
    elif call.data == "acc_antiphishing_remove":
        data['anti_phishing_code'] = ''
        save_data()
        send_temp_message(call.message.chat.id, "✅ Anti-phishing code removed.")
    elif call.data == "acc_sessions":
        sessions = data.setdefault('active_bot_sessions', [])
        current = sessions[-5:] if sessions else []
        lines = ["📱 *ACTIVE BOT SESSION*", "", "Telegram Bot API cannot enumerate or terminate the Telegram app's device sessions. This screen manages bot login sessions only."]
        if current:
            for s in current:
                lines.append(f"• Session `{s.get('id','N/A')}` — {s.get('time','N/A')}")
        else:
            lines.append("• No stored bot sessions.")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🚪 Log Out Current Bot Session", callback_data="acc_logout_current"))
        send_temp_message(call.message.chat.id, "\n".join(lines), reply_markup=markup)
    elif call.data == "acc_logout_current":
        data['logged_in'] = False
        data['last_login_time'] = 0
        save_data()
        send_temp_message(call.message.chat.id, "🚪 Current bot session has been logged out.", reply_markup=registration_or_login_markup(True))
    elif call.data == "acc_reinvest":
        data['auto_reinvest'] = not bool(data.get('auto_reinvest', False))
        save_data()
        send_temp_message(call.message.chat.id, f"📈 Auto-Reinvest is now {'ON' if data['auto_reinvest'] else 'OFF'}. Maturity will {'compound automatically' if data['auto_reinvest'] else 'credit capital and profit to your main balance'}.")
    elif call.data == "acc_delete_account":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🗑 Confirm Delete", callback_data="acc_delete_confirm"), types.InlineKeyboardButton("Cancel", callback_data="acc_delete_cancel"))
        send_temp_message(call.message.chat.id, "⚠️ *DELETE ACCOUNT*\n\nThis removes your bot profile and stored account data. Active investments must be settled before deletion. Continue?", reply_markup=markup)
    elif call.data == "acc_delete_confirm":
        if data.get('active_plans'):
            send_temp_message(call.message.chat.id, "❌ Account deletion is blocked while active investments exist. Please wait for settlement or contact administration.")
            return
        users.pop(user_id, None)
        for key in list(pending_withdrawals):
            if pending_withdrawals[key].get('user_id') == user_id:
                req = pending_withdrawals.pop(key)
                # Refund any balance reserved for an unfinished withdrawal.
                data['balance'] = round(float(data.get('balance', 0.0)) + float(req.get('amount', 0.0)), 2)
        for key in list(pending_deposits):
            if pending_deposits[key].get('user_id') == user_id:
                pending_deposits.pop(key, None)
        save_data()
        send_temp_message(call.message.chat.id, "🗑 Account deleted successfully.", reply_markup=registration_or_login_markup(False))
    elif call.data == "acc_delete_cancel":
        send_temp_message(call.message.chat.id, "Account deletion cancelled.")
    elif call.data == "acc_settings_back":
        send_temp_message(call.message.chat.id, "⚙️ *ACCOUNT SETTINGS*", reply_markup=account_settings_inline_markup())
    elif call.data == "acc_back_login":
        send_temp_message(call.message.chat.id, "🔐 Please use the login option below.", reply_markup=registration_or_login_markup(True))

def account_change_password_current(message):
    delete_user_secret_message(message)
    data = get_user_data(message.from_user.id)
    if not verify_password_secure(data.get('password',''), (message.text or '').strip()):
        msg = send_temp_message(message.chat.id, "❌ Current password is incorrect. Enter your current password again:")
        bot.register_next_step_handler(msg, account_change_password_current)
        return
    msg = send_temp_message(message.chat.id, "🔐 Current password verified. Enter your new account password:")
    bot.register_next_step_handler(msg, account_change_password_new)

def account_change_password_new(message):
    delete_user_secret_message(message)
    new_password=(message.text or '').strip()
    if len(new_password) < 4:
        msg=send_temp_message(message.chat.id,"❌ Password must contain at least 4 characters. Enter a new password:")
        bot.register_next_step_handler(msg, account_change_password_new)
        return
    data=get_user_data(message.from_user.id)
    data['password']=hash_password_secure(new_password)
    data['failed_login_attempts']=0
    save_data()
    send_temp_message(message.chat.id,"✅ Account password changed successfully.")

def save_antiphishing_code(message):
    delete_user_secret_message(message)
    code=(message.text or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9\-_.]{3,20}', code):
        msg=send_temp_message(message.chat.id,"❌ Use 3–20 letters, numbers, hyphens, underscores or dots:")
        bot.register_next_step_handler(msg, save_antiphishing_code)
        return
    data=get_user_data(message.from_user.id)
    data['anti_phishing_code']=code
    save_data()
    send_temp_message(message.chat.id,"✅ Anti-phishing code saved. It will appear in official security notifications.")

def save_trc20_wallet(message):
    user_id = message.from_user.id
    wallet = message.text.strip() if message.text else ""
    
    if not is_valid_trc20(wallet):
        msg = bot.send_message(
            message.chat.id, 
            "🛑 *INVALID TRC20 DESTINATION ADDRESS!*\n\n"
            "┌────────────────────────────────────────┐\n"
            "│ Addresses must begin with 'T' and be   │\n"
            "│ exactly 34 characters long.            │\n"
            "└────────────────────────────────────────/\n\n"
            "Please submit a valid TRC20 wallet address:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, save_trc20_wallet)
        return

    data = get_user_data(user_id, username=message.from_user.username)
    data['wallet'] = wallet
    save_data()
    
    wallet_box_text = (
        f"✅ *TRC20 WALLET REGISTERED SUCCESSFULLY:*\n"
        f"┌────────────────────────────────────────┐\n"
        f"│ `{mask_wallet(wallet)}`                  │\n"
        f"└────────────────────────────────────────┘"
    )
    bot.send_message(message.chat.id, wallet_box_text, parse_mode="Markdown")

def save_user_payment_account(message, mid):
    """Save the user's own account number for an admin-added payment method."""
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if text.startswith("/"):
        send_temp_message(message.chat.id, "❎ Cancelled.")
        return
    m = get_payment_methods().get(mid)
    if not m or m.get("builtin") or not m.get("enabled", True):
        send_temp_message(message.chat.id, "❌ This payment method is currently unavailable.")
        return
    if len(text) < 3 or len(text) > 100:
        msg = send_temp_message(
            message.chat.id,
            f"🛑 *INVALID ACCOUNT NUMBER!*\nEnter a valid *{pm_escape(m['name'])}* account number (3–100 characters):",
            delay=120)
        bot.register_next_step_handler(msg, save_user_payment_account, mid)
        return
    data = get_user_data(user_id, username=message.from_user.username)
    data.setdefault('payment_accounts', {})[mid] = {'name': m['name'], 'account': text}
    save_data()
    send_temp_message(
        message.chat.id,
        f"✅ *{pm_escape(m['name'])} ACCOUNT SAVED SUCCESSFULLY:*\n"
        f"┌────────────────────────────────────────┐\n"
        f"│ `{text.replace(chr(96), '')}`\n"
        f"└────────────────────────────────────────┘")

# --- ADMIN PANEL HANDLER ---
@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
def admin_panel_handler(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    total_users = len(users)
    total_dep = sum(u.get('total_deposited', 0.0) for u in users.values())
    total_wd = sum(u.get('total_withdrawn', 0.0) for u in users.values())
    total_inv = sum(u.get('total_invested', 0.0) for u in users.values())

    admin_header = (
        f"👑 *ADMIN PANEL DASHBOARD*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *TOTAL REGISTERED USERS:* `{total_users}`\n"
        f"📥 *TOTAL SYSTEM DEPOSITS:* `${total_dep:.2f}`\n"
        f"📤 *TOTAL SYSTEM WITHDRAWALS:* `${total_wd:.2f}`\n"
        f"📊 *TOTAL SYSTEM INVESTMENTS:* `${total_inv:.2f}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    admin_user_boxes = f"📋 *RECENT USER DATABASE LIST:*\n\n"

    for uid, udata in users.items():
        uname = udata.get('username', 'N/A')
        username_str = f"@{uname}" if uname != 'N/A' and not uname.startswith('@') else uname
        banned_status = "🔴 BANNED" if udata.get('banned', False) else "🟢 ACTIVE"
        
        admin_user_boxes += (
            f"┌────────────────────────────────────────┐\n"
            f"│ 👤 *USER ID:* `{uid}`\n"
            f"│ 🏷 *TELEGRAM USERNAME:* {username_str}\n"
            f"│ 🔑 *PASSWORD:* `{udata.get('password', 'N/A')}`\n"
            f"│ 📊 *STATUS:* {banned_status}\n"
            f"│ 💵 *AVAILABLE BALANCE:* `${udata.get('balance', 0.0):.2f}`\n"
            f"│ 📊 *TOTAL INVESTED:* `${udata.get('total_invested', 0.0):.2f}`\n"
            f"│ 📥 *TOTAL DEPOSITED:* `${udata.get('total_deposited', 0.0):.2f}`\n"
            f"│ 📤 *TOTAL WITHDRAWN:* `${udata.get('total_withdrawn', 0.0):.2f}`\n"
            f"│ 🎟 *WITHDRAW PERMISSIONS:* `{udata.get('withdrawal_permissions', 0)}`\n"
            f"│ 💳 *WALLET ADDRESS:* `{udata.get('wallet', 'Not Set')}`\n"
            f"└────────────────────────────────────────┘\n\n"
        )

    full_admin_text = admin_header + admin_user_boxes

    if len(full_admin_text) > 4000:
        for x in range(0, len(full_admin_text), 4000):
            bot.send_message(message.chat.id, full_admin_text[x:x+4000], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, full_admin_text, parse_mode="Markdown")

    bot.send_message(
        message.chat.id,
        "⚙️ *ADMIN MANAGEMENT ACTIONS MENU:*\nChoose a supervisory control below:",
        parse_mode="Markdown",
        reply_markup=admin_panel_inline_markup()
    )

# --- ADMIN FEATURE 1: CHANGE USER PASSWORD ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_change_password")
def admin_start_password_change(call):
    if call.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "🔍 *ADMIN PASSWORD CHANGE*\n\n"
        "Please submit target search criteria:\n"
        "• Telegram Username (e.g. `@username`)\n"
        "• Telegram User ID (e.g. `123456789`)\n"
        "• Available Balance:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_process_search_password)

def admin_process_search_password(message):
    query = message.text.strip() if message.text else ""
    matched_users = search_users_by_query(query)

    if not matched_users:
        bot.send_message(message.chat.id, f"❌ No user profile matched query: `{query}`", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, udata in matched_users:
        btn_text = f"👤 ID: {uid} | @{udata.get('username','N/A')} | ${udata.get('balance',0.0):.2f}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_select_pw_{uid}"))

    bot.send_message(message.chat.id, "🎯 *Select Target User Profile:*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_select_pw_"))
def admin_select_user_for_password(call):
    if call.from_user.id != ADMIN_ID:
        return
    target_id = int(call.data.replace("adm_select_pw_", ""))
    bot.answer_callback_query(call.id)

    udata = get_user_data(target_id)
    msg = bot.send_message(
        call.message.chat.id,
        f"🔑 *SET NEW USER PASSWORD*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"🏷 *Username:* `@{udata.get('username', 'N/A')}`\n\n"
        f"Please input the **NEW Password** for this user (minimum 4 characters):",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_execute_password_change, target_id)

def admin_execute_password_change(message, target_id):
    new_password = message.text.strip() if message.text else ""
    # Remove the password from the admin chat right away.
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass

    if len(new_password) < 4:
        msg = bot.send_message(message.chat.id, "❌ Password must be at least 4 characters. Please submit the new password again:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_execute_password_change, target_id)
        return

    udata = get_user_data(target_id)
    udata['password'] = hash_password_secure(new_password)
    udata['failed_login_attempts'] = 0
    udata['logged_in'] = False
    udata['last_login_time'] = 0
    save_data()

    bot.send_message(
        message.chat.id,
        f"✅ *USER PASSWORD CHANGED SUCCESSFULLY!*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"🏷 *Username:* `@{udata.get('username', 'N/A')}`\n\n"
        f"Please share the new password with the user privately.",
        parse_mode="Markdown"
    )

    try:
        bot.send_message(target_id, "🔑 *PASSWORD UPDATED BY ADMINISTRATION!*\n\nYour account password has been changed. Please log in with the new password provided by Customer Service.", parse_mode="Markdown")
    except Exception:
        pass

# --- ADMIN FEATURE 2: CANCEL USER INVESTMENT & REFUND ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_cancel_inv")
def admin_start_cancel_investment(call):
    if call.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "🚫 *ADMIN INVESTMENT CANCELLATION & REFUND PROTOCOL*\n\n"
        "Please submit search criteria to locate user:\n"
        "• Telegram Username\n"
        "• Telegram User ID\n"
        ""
        "• Balance",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_process_search_inv)

def admin_process_search_inv(message):
    query = message.text.strip() if message.text else ""
    matched_users = search_users_by_query(query)

    if not matched_users:
        bot.send_message(message.chat.id, f"❌ No user profile matched: `{query}`", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, udata in matched_users:
        active_cnt = len(udata.get('active_plans', []))
        btn_text = f"👤 ID: {uid} | @{udata.get('username','N/A')} | Active Plans: {active_cnt}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_select_inv_{uid}"))

    bot.send_message(message.chat.id, "🎯 *Select User Profile for Investment Audit:*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_select_inv_"))
def admin_list_user_investments(call):
    if call.from_user.id != ADMIN_ID:
        return
    target_id = int(call.data.replace("adm_select_inv_", ""))
    bot.answer_callback_query(call.id)

    udata = get_user_data(target_id)
    active_plans = udata.get('active_plans', [])

    if not active_plans:
        bot.send_message(call.message.chat.id, f"⚠️ User ID `{target_id}` currently maintains no active investment positions.", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, plan in enumerate(active_plans):
        btn_text = f"❌ Terminate: {plan.get('plan')} (${plan.get('amount', 0.0):.2f})"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_do_cancel_inv_{target_id}_{idx}"))

    bot.send_message(
        call.message.chat.id,
        f"📊 *ACTIVE PORTFOLIO POSITIONS FOR USER `{target_id}`:*\n"
        f"Select a position below to terminate and instantly refund capital to balance:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_do_cancel_inv_"))
def admin_execute_cancel_investment(call):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    target_id = int(parts[4])
    plan_index = int(parts[5])

    bot.answer_callback_query(call.id)
    udata = get_user_data(target_id)
    active_plans = udata.get('active_plans', [])

    if plan_index >= len(active_plans):
        bot.send_message(call.message.chat.id, "❌ Investment position not found or already terminated.")
        return

    plan = active_plans.pop(plan_index)
    inv_amount = plan.get('amount', 0.0)
    plan_name = plan.get('plan', 'Investment Package')

    udata['balance'] += inv_amount
    add_transaction(target_id, "Investment Terminated", inv_amount, "Refunded", f"Plan: {plan_name} (Admin Cancelled)")
    save_data()

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.send_message(
        call.message.chat.id,
        f"✅ *INVESTMENT TERMINATED & CAPITAL REFUNDED!*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"📦 *Terminated Plan:* `{plan_name}`\n"
        f"💰 *Refund Amount:* `${inv_amount:.2f}`\n"
        f"💵 *Updated Balance:* `${udata['balance']:.2f}`",
        parse_mode="Markdown"
    )

    try:
        bot.send_message(
            target_id,
            f"🚫 **INVESTMENT TERMINATED & CAPITAL REFUNDED**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Dear Investor,\n"
            f"Your active investment position **{plan_name}** (${inv_amount:.2f}) has been terminated by administration.\n\n"
            f"💰 **FULL CAPITAL REVERSAL:** `${inv_amount:.2f}` has been securely credited back to your active balance.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

# --- ADMIN FEATURE 3: SET WITHDRAWAL PERMISSIONS ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_set_wd_perm")
def admin_start_wd_permission(call):
    if call.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "🎟 *CONFIGURE WITHDRAWAL ALLOWANCES SYSTEM*\n\n"
        "Please submit target search criteria:\n"
        "• Telegram Username\n"
        "• Telegram User ID",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_process_search_perm)

def admin_process_search_perm(message):
    query = message.text.strip() if message.text else ""
    matched_users = search_users_by_query(query)

    if not matched_users:
        bot.send_message(message.chat.id, f"❌ No user profile matched: `{query}`", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, udata in matched_users:
        current_p = udata.get('withdrawal_permissions', 0)
        btn_text = f"👤 ID: {uid} | @{udata.get('username','N/A')} | Current Allowances: {current_p}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_select_perm_{uid}"))

    bot.send_message(message.chat.id, "🎯 *Select Target User Profile:*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_select_perm_"))
def admin_select_user_for_perm(call):
    if call.from_user.id != ADMIN_ID:
        return
    target_id = int(call.data.replace("adm_select_perm_", ""))
    bot.answer_callback_query(call.id)

    udata = get_user_data(target_id)
    msg = bot.send_message(
        call.message.chat.id,
        f"🎟 *CONFIGURE WITHDRAWAL ALLOWANCE COUNT*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"🏷 *Username:* `@{udata.get('username', 'N/A')}`\n"
        f"📊 *Current Allowances:* `{udata.get('withdrawal_permissions', 0)}`\n\n"
        f"Please enter the **number of withdrawal allowances** to grant (e.g., `1`, `2`, `5`):",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_execute_set_perm, target_id)

def admin_execute_set_perm(message, target_id):
    try:
        count = int(message.text.strip())
        if count < 0:
            count = 0
            
        udata = get_user_data(target_id)
        udata['withdrawal_permissions'] = count
        save_data()

        bot.send_message(
            message.chat.id,
            f"✅ *WITHDRAWAL ALLOWANCES UPDATED!*\n\n"
            f"👤 *User ID:* `{target_id}`\n"
            f"🎟 *Total Granted Allowances:* `{count}`",
            parse_mode="Markdown"
        )

        try:
            bot.send_message(
                target_id,
                f"🎟 *WITHDRAWAL ALLOWANCE GRANTED BY ADMINISTRATION!*\n\n"
                f"Administration has granted you **{count}** special withdrawal allowance(s). You may now request payout.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid numeric format. Operation aborted.")

# --- ADMIN FEATURE 4: USER BAN & UNBAN SYSTEM ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_ban_manager")
def admin_ban_manager_start(call):
    if call.from_user.id != ADMIN_ID:
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "🔨 *ADMIN USER BAN & UNBAN SYSTEM*\n\n"
        "Please submit search criteria to locate user for suspension/reinstatement:\n"
        "• Telegram Username\n"
        "• Telegram User ID",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, admin_process_search_ban)

def admin_process_search_ban(message):
    query = message.text.strip() if message.text else ""
    matched_users = search_users_by_query(query)

    if not matched_users:
        bot.send_message(message.chat.id, f"❌ No user matched search query: `{query}`", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, udata in matched_users:
        status_txt = "🔴 BANNED" if udata.get('banned', False) else "🟢 ACTIVE"
        btn_text = f"👤 ID: {uid} | @{udata.get('username','N/A')} | {status_txt}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_select_ban_{uid}"))

    bot.send_message(message.chat.id, "🎯 *Select User Profile to Manage Suspension:*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_select_ban_"))
def admin_select_user_for_ban(call):
    if call.from_user.id != ADMIN_ID:
        return
    target_id = int(call.data.replace("adm_select_ban_", ""))
    bot.answer_callback_query(call.id)

    udata = get_user_data(target_id)
    is_currently_banned = udata.get('banned', False)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_currently_banned:
        btn_action = types.InlineKeyboardButton("🟢 Unban User", callback_data=f"adm_do_unban_{target_id}")
    else:
        btn_action = types.InlineKeyboardButton("🔴 Ban User", callback_data=f"adm_do_ban_{target_id}")
    markup.add(btn_action)

    status_str = "🔴 Banned / Suspended" if is_currently_banned else "🟢 Active / Operating"
    bot.send_message(
        call.message.chat.id,
        f"🔨 *USER SUSPENSION CONTROL PANEL*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"🏷 *Username:* `@{udata.get('username', 'N/A')}`\n"
        f"📊 *Current Status:* `{status_str}`\n\n"
        f"Select action below:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_do_ban_") or call.data.startswith("adm_do_unban_"))
def admin_execute_ban_action(call):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    action = parts[2] # 'ban' or 'unban'
    target_id = int(parts[3])

    bot.answer_callback_query(call.id)
    udata = get_user_data(target_id)

    if action == "ban":
        udata['banned'] = True
        save_data()
        bot.send_message(call.message.chat.id, f"✅ *User ID `{target_id}` has been successfully BANNED/SUSPENDED.*", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "🛑 **ACCOUNT SUSPENDED:** Your user profile has been suspended by administration.", parse_mode="Markdown")
        except Exception:
            pass
    else:
        udata['banned'] = False
        save_data()
        bot.send_message(call.message.chat.id, f"✅ *User ID `{target_id}` has been successfully UNBANNED/REINSTATED.*", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "🟢 **ACCOUNT REINSTATED:** Your user profile suspension has been lifted by administration.", parse_mode="Markdown")
        except Exception:
            pass

# --- MAIN MENU BUTTON HANDLERS ---
MAIN_ACTION_KEYS = ['dashboard','history','investments','referral','deposit','withdraw','about','settings','support','logout','card']
MAIN_ACTION_TEXTS = {text for key in MAIN_ACTION_KEYS for text in localized_action_texts(key)}

@bot.message_handler(func=lambda message: message.text in MAIN_ACTION_TEXTS)
def generic_button_handler(message):
    user_id = message.from_user.id
    username = message.from_user.username
    data = get_user_data(user_id, username=username)
    action_key = next((key for key in MAIN_ACTION_KEYS if message.text in localized_action_texts(key)), None)

    if data.get('banned', False):
        bot.send_message(message.chat.id, "🛑 **ACCESS RESTRICTED:** Your user profile has been suspended by administration.", parse_mode="Markdown")
        return

    if action_key == "logout":
        if not data.get('registered', False):
            bot.send_message(message.chat.id, "⚠️ No active registration profile found.", parse_mode="Markdown")
            return
        
        data['logged_in'] = False
        save_data()
        bot.send_message(
            message.chat.id,
            "🚪 *SECURE LOGOUT SUCCESSFUL!*\n\nYour active session has been terminated securely. Click below to login again:",
            parse_mode="Markdown",
            reply_markup=registration_or_login_markup(is_registered=True)
        )
        return

    if not is_subscribed(user_id):
        bot.send_message(message.chat.id, f"🛑 *Access Denied!*\nYou MUST join {CHANNEL_ID} first.", parse_mode="Markdown", reply_markup=get_verification_markup())
        return

    if not data['registered']:
        bot.send_message(message.chat.id, "⚠️ Please complete registration first!", reply_markup=registration_or_login_markup(False))
        return

    if not is_logged_in_valid(user_id):
        bot.send_message(message.chat.id, "🔑 Session expired or logged out. Please log in again!", reply_markup=registration_or_login_markup(True))
        return

    if action_key == "dashboard":
        user_uname = f"@{username}" if username else "N/A"
        date_today = get_current_date_only()
        
        active_plans = data.get('active_plans', [])
        starter_plans = [p for p in active_plans if 'Starter' in p.get('plan', '')]
        pro_plans = [p for p in active_plans if 'Pro' in p.get('plan', '') or 'VIP' in p.get('plan', '')]

        def get_plan_summary(plans, plan_name):
            if not plans:
                return f"└ 🔴 *{plan_name}:* `No Active Position`"
            total_sum = sum(p.get('amount', 0.0) for p in plans)
            latest_ts = max(p.get('timestamp', 0) for p in plans)
            cd_str = get_investment_countdown_by_timestamp(latest_ts)
            return f"├ 🟢 *{plan_name} Total:* `${total_sum:.2f}`\n└ ⏱ *24H Countdown:* {cd_str}"

        starter_info = get_plan_summary(starter_plans, "Starter Plan")
        pro_info = get_plan_summary(pro_plans, "VIP Pro Plan")

        # Total profit is calculated from the currently active investment positions.
        # Starter Plan: 5% daily ROI | VIP Pro Plan: 7% daily ROI
        starter_profit = sum(p.get('amount', 0.0) for p in starter_plans) * 0.05
        pro_profit = sum(p.get('amount', 0.0) for p in pro_plans) * 0.07
        total_profit = starter_profit + pro_profit

        dashboard_text = (
            f"╔═════════════════════════════════════╗\n"
            f"║    🏢 *{COMPANY_NAME}*    ║\n"
            f"║      📊 *INVESTOR DASHBOARD*        ║\n"
            f"╚═════════════════════════════════════╝\n"
            f"📅 *DATE:* `{date_today}`\n\n"
            f"👤 *ACCOUNT INFORMATION*\n"
            f"├ 🆔 *ID:* `{mask_id(user_id)}`\n"
            f"├ 🏷 *Username:* **{user_uname}**\n"
            f"└ 💳 *Wallet:* `{mask_wallet(data['wallet'])}`\n\n"
            f"💵 *AVAILABLE BALANCE*\n"
            f"└ 💰 `{format_user_balance(data['balance'], data.get('default_currency','USDT'))}`\n\n"
            f"📈 *TOTAL INVESTMENT*\n"
            f"└ 📊 `{format_user_balance(data['total_invested'], data.get('default_currency','USDT'))}`\n\n"
            f"🏆 *TOTAL PROFIT (LIFETIME):* `{format_user_balance(float(data.get('total_profit', 0.0)), data.get('default_currency','USDT'))}`\n\n"
            f"💰 *TOTAL PROFIT*\n"
            f"├ 🚀 *Starter Profit (5%):* `{format_user_balance(starter_profit, data.get('default_currency','USDT'))}`\n"
            f"├ 💎 *VIP Pro Profit (7%):* `{format_user_balance(pro_profit, data.get('default_currency','USDT'))}`\n"
            f"└ 📊 *Total Profit:* `{format_user_balance(total_profit, data.get('default_currency','USDT'))}`\n\n"
            f"🚀 *STARTER PLAN STATUS*\n"
            f"{starter_info}\n\n"
            f"💎 *VIP PRO PLAN STATUS*\n"
            f"{pro_info}\n\n"
            f"📥 *TOTAL DEPOSIT*\n"
            f"└ 💳 `{format_user_balance(data['total_deposited'], data.get('default_currency','USDT'))}`\n\n"
            f"📤 *TOTAL WITHDRAW*\n"
            f"└ 💸 `{format_user_balance(data['total_withdrawn'], data.get('default_currency','USDT'))}`\n\n"
            f"💸 *{tr(user_id, 'total_fee', 'TOTAL FEE')}*\n"
            f"└ 💰 `{format_user_balance(float(data.get('total_fees', 0.0)), data.get('default_currency','USDT'))}`\n\n"
            f"🎁 *REFERRAL EARNINGS*\n"
            f"└ 🤝 `${data['referral_earnings']:.2f}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(message.chat.id, dashboard_text, parse_mode="Markdown")

    elif action_key == "settings":
        settings_text = (
            f"⚙️ *{tr(user_id, 'account_settings', 'ACCOUNT SETTINGS & SECURITY')}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 *GATEWAY:* `{data.get('wallet_gateway','USDT TRC20')}`\n"
            f"📍 *WALLET:* `{mask_wallet(data['wallet'])}`\n"
            f"💱 *DEFAULT CURRENCY:* `{data.get('default_currency','USDT')}`\n"
            f"🔁 *AUTO-REINVEST:* `{'ON' if data.get('auto_reinvest') else 'OFF'}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select a setting below:"
        )
        bot.send_message(message.chat.id, settings_text, parse_mode="Markdown", reply_markup=account_settings_inline_markup())

    elif action_key == "history":
        now_ts = datetime.now().timestamp()
        ninety_days_sec = 90 * 24 * 3600
        
        recent_txs = [tx for tx in data['transactions'] if (now_ts - tx.get('timestamp', now_ts)) <= ninety_days_sec]
        
        if not recent_txs:
            bot.send_message(message.chat.id, "📜 *No recorded transactions within the preceding 90-day ledger period.*", parse_mode="Markdown")
            return
            
        history_text = f"📜 *90-DAY AUDITED TRANSACTION LEDGER*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        display_txs = recent_txs[-15:]
        for idx, tx in enumerate(display_txs, 1):
            history_text += (
                f"┌────────────────────────────────────────┐\n"
                f"│ 📌 *{idx}. {tx['type']}*\n"
                f"│ 💰 *AMOUNT:* `${tx['amount']:.2f}`\n"
                f"│ 📅 *TIMESTAMP:* `{tx['date']}`\n"
                f"│ 🏷 *STATUS:* `{tx['status']}`\n"
            )
            if tx['details']:
                history_text += f"│ 📝 *REMARKS:* `{tx['details']}`\n"
            history_text += f"└────────────────────────────────────────┘\n\n"
            
        bot.send_message(message.chat.id, history_text, parse_mode="Markdown")

    elif action_key == "investments":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 Starter Plan (5% Daily ROI)", callback_data="invest_starter"),
            types.InlineKeyboardButton("💎 VIP Pro Plan (7% Daily ROI)", callback_data="invest_vip")
        )
        text = (
            f"📈 *{COMPANY_NAME} INVESTMENT PACKAGES*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ *STARTER PLAN*\n"
            "• Daily ROI: 5%\n"
            "• Investment Limits: $10 – $500\n"
            "• Withdrawal Limit: 2 Times per 24 Hours\n\n"
            "2️⃣ *VIP PRO PLAN*\n"
            "• Daily ROI: 7%\n"
            "• Investment Limits: $501 – Unlimited\n"
            "• Withdrawal Limit: 3 Times per 24 Hours\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select an investment tier below to deploy capital:"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    elif action_key == "referral":
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        ref_text = (
            f"🎁 *AFFILIATE REFERRAL PROTOCOL*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Earn a secure **1% Direct Commission** on every capital deposit executed by your invited partners.\n\n"
            "🔗 *YOUR AFFILIATE INVITATION LINK:*\n"
            f"`{ref_link}`\n\n"
            f"👥 *TOTAL INVITED PARTNERS:* `{data['referrals_count']}`\n"
            f"💵 *TOTAL COMMISSION EARNED:* `${data['referral_earnings']:.2f}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(message.chat.id, ref_text, parse_mode="Markdown")

    elif action_key == "deposit":
        text = (
            f"📥 *CAPITAL DEPOSIT GATEWAY*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *MINIMUM DEPOSIT REQUIREMENT:* `${MIN_DEPOSIT:.2f}`\n\n"
            "Select quick deposit amount or specify custom value below:"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=deposit_quick_markup())

    elif action_key == "withdraw":
        if data['balance'] < MIN_WITHDRAW:
            bot.send_message(
                message.chat.id, 
                f"🛑 *WITHDRAWAL REJECTED: INSUFFICIENT BALANCE!* 🛑\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 *YOUR ACTIVE BALANCE:* `${data['balance']:.2f}`\n"
                f"⚠️ *MINIMUM REQUIRED THRESHOLD:* `${MIN_WITHDRAW:.2f}`\n\n"
                f"Your balance does not meet the minimum payout criteria.", 
                parse_mode="Markdown"
            )
            return

        _wd_methods = enabled_payment_methods()
        if not _wd_methods:
            bot.send_message(
                message.chat.id,
                "🚫 *WITHDRAWALS TEMPORARILY UNAVAILABLE*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nNo payout method is currently active. Please try again later or contact support.",
                parse_mode="Markdown"
            )
            return
        _wd_custom = [(_mid, _m) for _mid, _m in _wd_methods if _mid != DEFAULT_METHOD_ID]
        _wd_saved = data.get('payment_accounts', {})
        _wd_alt_ok = any(_wd_saved.get(_mid, {}).get('account') for _mid, _m in _wd_custom)
        _wd_usdt_ok = any(_mid == DEFAULT_METHOD_ID for _mid, _m in _wd_methods) and is_valid_trc20(data['wallet'])
        if not _wd_usdt_ok and not _wd_alt_ok:
            if _wd_custom:
                _wd_err = "❌ *No Payout Account Configured!*\nPlease save a payout account (wallet address / account number) via '⚙️ Account Settings → 💳 Wallet / Address Settings' first."
            else:
                _wd_err = "❌ *TRC20 Destination Wallet Address Unconfigured or Invalid!*\nPlease register a valid TRC20 wallet via '⚙️ Account Settings' first."
            bot.send_message(message.chat.id, _wd_err, parse_mode="Markdown")
            return

        user_permissions = data.get('withdrawal_permissions', 0)

        if user_permissions <= 0 and user_id != ADMIN_ID:
            now_ts = datetime.now().timestamp()
            w_history = [t for t in data.get('withdrawal_timestamps', []) if (now_ts - t) < 86400]
            data['withdrawal_timestamps'] = w_history
            save_data()

            has_pro = any('Pro' in p.get('plan', '') or 'VIP' in p.get('plan', '') for p in data.get('active_plans', []))

            if has_pro:
                # Pro Plan: 3 withdrawals per 24 hours
                if len(w_history) >= 3:
                    bot.send_message(
                        message.chat.id,
                        "❌ **DAILY WITHDRAWAL LIMIT REACHED!**\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "As a **VIP Pro Plan** subscriber, your maximum daily allowance is **3 withdrawals per 24 hours**.\n\n"
                        "You have reached your daily ceiling. Please try again after 24 hours.",
                        parse_mode="Markdown"
                    )
                    return
            else:
                # Starter Plan: 2 withdrawals per 24 hours
                if len(w_history) >= 2:
                    bot.send_message(
                        message.chat.id,
                        "❌ **DAILY WITHDRAWAL LIMIT REACHED!**\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "**Starter Plan** members are permitted a maximum of **2 withdrawals per 24 hours**.\n\n"
                        "You have exhausted your daily quota. Upgrade to **VIP Pro Plan** for enhanced transactional limits or try again tomorrow!",
                        parse_mode="Markdown"
                    )
                    return
        
        text = (
            f"📤 *QUICK WITHDRAWAL GATEWAY*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 *AVAILABLE BALANCE:* `${data['balance']:.2f}`\n"
            + (f"💳 *TRC20 DESTINATION WALLET:* `{mask_wallet(data['wallet'])}`\n" if not _wd_custom else "💳 *PAYOUT METHOD:* choose after selecting the amount\n") +
            f"⚠️ *MINIMUM WITHDRAWAL:* `${MIN_WITHDRAW:.2f}`\n\n"
            "Select quick payout amount or specify custom value below:"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=withdraw_quick_markup())


    elif action_key == "card":
        card = _card_defaults(data)
        if card.get("admin_frozen") or card.get("status") == "FROZEN":
            first_cvc = None
        elif card.get("status") != "ACTIVE":
            card, first_cvc = issue_virtual_card(user_id)
        else:
            first_cvc = None
        border = "╔══════════════════════════════════╗\n"
        bottom = "╚══════════════════════════════════╝"
        card_text = (
            f"{border}"
            "║ 💳 *JUST CARD*                  ║\n"
            "║━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━══║\n"
            f"║ 🪪 Card: `{_mask_card_number(card.get('number'))}`\n"
            f"║ 📅 Expiry: `{card.get('expiry','')}`\n"
            "║ 🔐 CVC: `•••`\n"
            f"║ 📌 Status: `{card.get('status')}`\n"
            f"║ 🔒 PIN: `{'SET' if card.get('pin_set') else 'NOT SET'}`\n"
            f"{bottom}"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🔐 Set / Change Card PIN", callback_data="card_set_pin"),
            types.InlineKeyboardButton("👁 View Card Details (PIN)", callback_data="card_secure_view")
        )
        send_card_temp_message(message.chat.id, card_text, reply_markup=markup)
        if first_cvc:
            send_card_temp_message(
                message.chat.id,
                "🔐 *CARD CVC*\nThis CVC remains permanently linked to this card.\n"
                f"CVC: `{first_cvc}`"
            )

    elif action_key == "about":
        about_text = (
            f"🏢 *{COMPANY_NAME}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🌟 *Premier Global Capital Management & Institutional Real Estate Enterprise*\n\n"
            f"Welcome to **{COMPANY_NAME}**, built upon institutional security, technological innovation, and verified asset management.\n\n"
            "💎 *Why Elite Investors Choose Us?*\n"
            "• 🛡 **100% Capital-Backed Security:** All investment positions secured by physical institutional reserves.\n"
            "• ⚡ **Automated Daily Dividends:** Guaranteed high-yield returns credited precisely every 24 hours.\n"
            "• 🔐 **Institutional Transparency:** Rapid automated payouts and verifiable channel audit ledger.\n\n"
            "Construct your financial future with absolute confidence!"
        )
        bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

    elif action_key == "support":
        support_text = (
            f"🎧 *CLIENT SUPPORT DESK*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Welcome to our Institutional Client Support Center!\n\n"
            f"Should you encounter any technical inquiries regarding deposits, withdrawals, or account parameters, "
            f"our official client relations desk operates 24/7.\n\n"
            f"Please click the button below to connect directly with our Support Administrator.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Connect with Support Admin", url=SUPPORT_URL))
        bot.send_message(message.chat.id, support_text, parse_mode="Markdown", reply_markup=markup)

# --- DEPOSIT / WITHDRAWAL HISTORY ---
def _history_status_icon(status):
    s=str(status).lower()
    if any(x in s for x in ('cancel','reject','failed','refund')): return '🔴'
    if any(x in s for x in ('pending','audit','processing')): return '🔵'
    return '🟢'

def show_filtered_history(chat_id, user_id, kind):
    data=get_user_data(user_id)
    txs=[]
    for tx in data.get('transactions',[]):
        typ=str(tx.get('type','')).lower()
        if (kind=='deposit' and 'deposit' in typ) or (kind=='withdrawal' and 'withdraw' in typ):
            txs.append(tx)
    lines=[f"📜 *{kind.upper()} HISTORY*","━━━━━━━━━━━━━━━━━━━━"]
    if not txs:
        lines.append("No matching transaction records found.")
    else:
        for tx in txs[-15:][::-1]:
            lines.append(f"{_history_status_icon(tx.get('status'))} `{tx.get('date','N/A')}` — `{tx.get('status','N/A')}` — `${float(tx.get('amount',0.0)):.2f}`")
            if tx.get('details'): lines.append(f"   📝 {tx['details']}")
    send_temp_message(chat_id,'\n'.join(lines),delay=45)

@bot.callback_query_handler(func=lambda call: call.data in ('tx_history_deposit','tx_history_withdrawal'))
def transaction_history_callback(call):
    bot.answer_callback_query(call.id)
    kind='deposit' if call.data.endswith('deposit') else 'withdrawal'
    show_filtered_history(call.message.chat.id, call.from_user.id, kind)

# --- QUICK DEPOSIT FLOW WITH TRC20 AUTO CHECK ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_quick_"))
def handle_deposit_quick(call):
    val = call.data.replace("dep_quick_", "")
    bot.answer_callback_query(call.id)
    
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    
    if not enabled_payment_methods():
        bot.send_message(call.message.chat.id, PM_NONE_ENABLED_TEXT, parse_mode="Markdown")
        return

    if val == "custom":
        msg = bot.send_message(call.message.chat.id, f"📥 Please submit custom deposit capital amount (Minimum `${MIN_DEPOSIT:.2f}`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_deposit_amount_text)
    else:
        amount = float(val)
        start_deposit_with_method(call.message.chat.id, amount)

def process_deposit_amount_text(message):
    try:
        amount = float(message.text.strip())
        if amount < MIN_DEPOSIT:
            bot.send_message(message.chat.id, f"❌ Minimum deposit threshold is `${MIN_DEPOSIT:.2f}`.", parse_mode="Markdown")
            return
        start_deposit_with_method(message.chat.id, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid format. Please submit a numerical value.")

def proceed_deposit_payment(chat_id, amount):
    text = (
        f"📥 *DEPOSIT PAYMENT SPECIFICATION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *CAPITAL AMOUNT:* `${amount:.2f}`\n"
        f"🌐 *NETWORK PROTOCOL:* `USDT (TRC20)`\n\n"
        "🏦 *CORPORATE DEPOSIT ADDRESS*\n"
        "┌────────────────────────────────────────┐\n"
        f"│ `{USDT_ADDRESS}`\n"
        "└────────────────────────────────────────┘\n"
        "📋 *Tap and hold the address above to copy it.*\n\n"
        "⚠️ Please submit your **Transaction Hash (TxID)** below:"
    )
    msg = bot.send_message(chat_id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_deposit_txid, amount)

def process_deposit_txid(message, amount):
    txid = message.text.strip() if message.text else ""

    if not is_valid_txid(txid):
        msg = bot.send_message(
            message.chat.id,
            "🛑 *INVALID TRANSACTION HASH (TxID)!*\nPlease submit the TRON transaction hash:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_deposit_txid, amount)
        return

    txid = txid.strip()

    if txid in used_txids:
        bot.send_message(
            message.chat.id,
            "❌ *SECURITY AUDIT ERROR:* This TxID has already been submitted.",
            parse_mode="Markdown"
        )
        return

    status_msg = bot.send_message(
        message.chat.id,
        "⚡ *Verifying TRC20 USDT transaction...*\n"
        "Please wait while the blockchain is checked.",
        parse_mode="Markdown"
    )

    is_valid_onchain, verified_amt = verify_tron_usdt_onchain(txid, amount)

    try:
        bot.delete_message(message.chat.id, status_msg.message_id)
    except Exception:
        pass

    if is_valid_onchain:
        user_id = message.from_user.id
        used_txids.add(txid)
        data = get_user_data(user_id, username=message.from_user.username)
        data['balance'] += verified_amt
        data['total_deposited'] += verified_amt
        add_transaction(
            user_id, "Deposit", verified_amt,
            "Completed (Auto-Verified)",
            f"TxID: {mask_txid(txid)}"
        )

        if data.get('referred_by'):
            ref_id = data['referred_by']
            ref_data = get_user_data(ref_id)
            commission = verified_amt * 0.01
            ref_data['balance'] += commission
            ref_data['referral_earnings'] += commission
            add_transaction(
                ref_id, "Referral Commission", commission,
                "Completed", f"Partner ID: {mask_id(user_id)}"
            )
            try:
                bot.send_message(
                    ref_id,
                    f"🎁 *1% Affiliate Commission Received!* (`+${commission:.2f}`)",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        save_data()

        bot.send_message(
            message.chat.id,
            f"🎉 *DEPOSIT CONFIRMED — TRC20 USDT*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Credited:* `${verified_amt:.2f}`\n"
            f"🔗 *TxID:* `{mask_txid(txid)}`\n"
            f"✅ *Status:* Blockchain verified\n"
            f"💳 *Balance:* `${data['balance']:.2f}`",
            parse_mode="Markdown"
        )
        try:
            post_channel_deposit_success(user_id, verified_amt, txid)
            show_celebration_effect(message.chat.id)
        except Exception as e:
            print(f"Deposit success notification error: {e}")
        return

    # Automatic verification failed. Do not credit the balance.
    text = (
        f"📸 *DEPOSIT VERIFICATION REQUIRED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Requested Amount:* `${amount:.2f}`\n"
        f"🔗 *TxID:* `{mask_txid(txid)}`\n\n"
        "⚠️ The blockchain verifier could not confirm this transfer "
        "automatically.\n\n"
        "Please upload a clear screenshot of the completed USDT TRC20 transfer "
        "for *Manual Deposit Review*. The balance will remain unchanged until approval."
    )
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_deposit_screenshot, amount, txid)

def process_deposit_screenshot(message, amount, txid, method_id=None):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    if not message.photo:
        msg = bot.send_message(
            message.chat.id, 
            "⚠️ *IMAGE PROOF REQUIRED!* Please upload your payment screenshot image:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_deposit_screenshot, amount, txid, method_id)
        return

    show_100_percent_loading(message.chat.id, "SUBMITTING DEPOSIT REVIEW PROOF")

    photo_id = message.photo[-1].file_id
    # Reserve the TxID only after admin approval; rejected requests may be resubmitted.

    dep_id = f"D{int(datetime.now().timestamp())}{user_id % 1000}"
    pending_deposits[dep_id] = {
        'user_id': user_id,
        'amount': amount,
        'txid': txid
    }
    method_label = None
    if method_id and method_id != DEFAULT_METHOD_ID:
        _m = get_payment_methods().get(method_id, {})
        method_label = _m.get('name', method_id)
        pending_deposits[dep_id]['method_id'] = method_id
        pending_deposits[dep_id]['method_name'] = method_label
        pending_deposits[dep_id]['txid_key'] = f"{method_id}:{txid.lower()}"

    add_transaction(
        user_id, "Deposit", amount, "Pending Audit",
        f"TxID: {mask_txid(txid)}" if not method_label else f"{method_label} | Ref: {mask_txid(txid)}"
    )
    save_data()

    bot.send_message(
        message.chat.id,
        "✅ *DEPOSIT SUBMISSION RECEIVED*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Amount:* `${amount:.2f}`\n"
        f"🔗 *TxID:* `{mask_txid(txid)}`\n"
        "🟡 *Status:* `PENDING VERIFICATION`\n\n"
        "Your deposit proof has been submitted successfully. The transaction has not been credited to your balance yet.\n\n"
        "🔎 *What happens next?*\n"
        "• The administrator will review your TxID and payment screenshot.\n"
        "• Your balance will be credited only after the transaction is approved.\n"
        "• Please do not submit the same TxID again while it is under review.\n"
        "• Keep your transaction details available until verification is complete.",
        parse_mode="Markdown"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_approve = types.InlineKeyboardButton("✅ Approve", callback_data=f"dep_app_{dep_id}")
    btn_reject = types.InlineKeyboardButton("❌ Reject", callback_data=f"dep_rej_menu_{dep_id}")
    markup.add(btn_approve, btn_reject)

    # Admin request includes username, Telegram ID and wallet address.
    udata_info = get_user_data(user_id)
    admin_caption = (
        f"🚨 *NEW DEPOSIT REVIEW REQUEST*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *USER ID:* `{user_id}` (Masked: `{mask_id(user_id)}`)\n"
        f"🏷 *TELEGRAM USERNAME:* {username}\n"
        f"🆔 *TELEGRAM USER ID:* `{user_id}`\n"
        f"💳 *USER WALLET ADDRESS:* `{udata_info.get('wallet', 'Not Set')}`\n"
        f"💵 *REQUESTED:* `${amount:.2f}`\n"
        f"📅 *TIME:* `{get_current_time()}`\n"
        f"🔎 *REVIEW:* `MANUAL VERIFICATION REQUIRED`\n"
        + (f"💱 *PAYMENT METHOD:* {pm_escape(method_label)}\n" if method_label else "") +
        f"🔗 *TXID:* `{txid.replace(chr(96), '')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        sent = bot.send_photo(
            ADMIN_ID, photo_id, caption=admin_caption,
            parse_mode="Markdown", reply_markup=markup
        )
        pending_deposits[dep_id]['admin_message_id'] = sent.message_id
        save_data()
    except Exception as e:
        print(f"Error notifying admin with photo: {e}")
        # Fallback: never lose the pending request if Telegram rejects the photo.
        try:
            sent = bot.send_message(
                ADMIN_ID, admin_caption, parse_mode="Markdown",
                reply_markup=markup
            )
            pending_deposits[dep_id]['admin_message_id'] = sent.message_id
            pending_deposits[dep_id]['admin_notification_fallback'] = True
            save_data()
        except Exception as e2:
            print(f"Error notifying admin with fallback text: {e2}")
            bot.send_message(
                message.chat.id,
                "⚠️ Your deposit proof was saved for *Manual Deposit Review*, but the administrator notification could not be delivered. Please contact support."
            )


# ================= VIRTUAL CARD HANDLERS =================
@bot.callback_query_handler(func=lambda call: call.data == "card_set_pin")
def card_set_pin_start(call):
    data = get_user_data(call.from_user.id, username=call.from_user.username)
    card = _card_defaults(data)
    if card.get("admin_frozen") or card.get("status") == "FROZEN":
        bot.answer_callback_query(call.id, "Card is frozen. You cannot change the PIN until the administrator unfreezes the card.", show_alert=True)
        return
    if card.get("pin_set"):
        msg = send_card_temp_message(call.message.chat.id, '🔐 ' + tr(call.from_user.id, 'current_pin'))
        bot.register_next_step_handler(msg, card_verify_old_pin_for_change)
    else:
        msg = send_card_temp_message(call.message.chat.id, '🔐 ' + tr(call.from_user.id, 'new_pin'))
        bot.register_next_step_handler(msg, card_set_initial_pin)

def card_set_initial_pin(message):
    pin = (message.text or "").strip()
    delete_user_secret_message(message)
    latest = _card_defaults(get_user_data(message.from_user.id, username=message.from_user.username))
    if latest.get("admin_frozen") or latest.get("status") == "FROZEN":
        send_card_temp_message(message.chat.id, "🔒 Card is frozen. PIN changes are disabled until the administrator unfreezes the card.")
        return
    if set_virtual_card_pin(message.from_user.id, pin):
        send_card_temp_message(message.chat.id, "✅ Card PIN set successfully.")
    else:
        send_card_temp_message(message.chat.id, "❌ PIN must contain exactly 4 digits and the card must be active.")

def card_verify_old_pin_for_change(message):
    old_pin = (message.text or "").strip()
    delete_user_secret_message(message)
    data = get_user_data(message.from_user.id, username=message.from_user.username)
    card = _card_defaults(data)
    if card.get("admin_frozen") or card.get("status") == "FROZEN":
        send_card_temp_message(message.chat.id, "🔒 Card is frozen. PIN changes are disabled until the administrator unfreezes the card.")
        return
    if card.get("pin_hash") != _hash_card_secret(old_pin):
        send_card_temp_message(message.chat.id, '❌ ' + tr(message.from_user.id, 'pin_failed'))
        return
    msg = send_card_temp_message(message.chat.id, '🔐 ' + tr(message.from_user.id, 'pin_verified'))
    bot.register_next_step_handler(msg, card_save_changed_pin)

def card_save_changed_pin(message):
    new_pin = (message.text or "").strip()
    delete_user_secret_message(message)
    data = get_user_data(message.from_user.id, username=message.from_user.username)
    if _card_defaults(data).get("admin_frozen") or _card_defaults(data).get("status") == "FROZEN":
        send_card_temp_message(message.chat.id, "🔒 Card is frozen. PIN changes are disabled until the administrator unfreezes the card.")
        return
    if set_virtual_card_pin(message.from_user.id, new_pin):
        send_card_temp_message(message.chat.id, '✅ ' + tr(message.from_user.id, 'pin_changed'))
    else:
        send_card_temp_message(message.chat.id, "❌ New PIN must contain exactly 4 digits.")

@bot.callback_query_handler(func=lambda call: call.data == "card_secure_view")
def card_secure_view_start(call):
    bot.answer_callback_query(call.id)
    msg = send_card_temp_message(call.message.chat.id, "🔐 Enter your 4-digit card PIN to view card details:")
    bot.register_next_step_handler(msg, card_secure_view_verify)

def card_secure_view_verify(message):
    pin = (message.text or "").strip()
    delete_user_secret_message(message)
    data = get_user_data(message.from_user.id, username=message.from_user.username)
    card = _card_defaults(data)
    if card.get("status") != "ACTIVE":
        send_card_temp_message(message.chat.id, "❌ Card is not active.")
        return
    if card.get("pin_hash") != _hash_card_secret(pin):
        send_card_temp_message(message.chat.id, "❌ Incorrect card PIN. Card details were not shown.")
        return
    cvc = _decrypt_card_cvc(card.get("cvc_encrypted"))
    if cvc is None:
        send_card_temp_message(message.chat.id, "⚠️ CVC is unavailable for this legacy card. Please replace/reissue the card.")
        return
    border = "╔══════════════════════════════════╗\n"
    bottom = "╚══════════════════════════════════╝"
    details = (
        f"{border}"
        "║ 💳 *JUST CARD — SECURE VIEW*    ║\n"
        "║━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━══║\n"
        f"║ 🪪 Number: `{card.get('number','')}`\n"
        f"║ 📅 Expiry: `{card.get('expiry','')}`\n"
        f"║ 🔐 CVC: `{cvc}`\n"
        f"{bottom}"
    )
    send_card_temp_message(message.chat.id, details)



# ================= COMPLETE CARD WITHDRAWAL FLOW =================
def card_withdrawal_prepare(user_id, amount, destination):
    data = get_user_data(user_id)
    ok, reason = card_can_withdraw(data, amount)
    if not ok:
        return False, reason, None
    amount = float(amount)
    if data.get("balance", 0.0) < amount:
        return False, "Insufficient balance.", None

    request_id = f"CW{uuid.uuid4().hex[:18].upper()}"
    data["balance"] -= amount
    pending_withdrawals[request_id] = {
        "user_id": user_id,
        "amount": amount,
        "wallet": destination,
        "method": "VIRTUAL_CARD",
        "status": "Pending",
        "created_at": get_current_time(),
        "card_last4": _card_defaults(data).get("number", "")[-4:]
    }
    save_data()
    return True, "", request_id

def card_withdrawal_cancel(request_id):
    req = pending_withdrawals.pop(request_id, None)
    if not req:
        return False
    data = get_user_data(req["user_id"])
    data["balance"] += float(req["amount"])
    save_data()
    return True

def card_withdrawal_complete(request_id, tx_reference=""):
    req = pending_withdrawals.get(request_id)
    if not req:
        return False
    data = get_user_data(req["user_id"])
    record_card_withdrawal(data, req["amount"])
    add_transaction(
        req["user_id"], "Card Withdrawal", req["amount"], "Completed",
        f"Card withdrawal {tx_reference}".strip()
    )
    pending_withdrawals.pop(request_id, None)
    save_data()
    return True

def card_withdrawal_reject(request_id, reason="Rejected by admin"):
    req = pending_withdrawals.pop(request_id, None)
    if not req:
        return False
    data = get_user_data(req["user_id"])
    data["balance"] += float(req["amount"])
    add_transaction(
        req["user_id"], "Card Withdrawal Refund",
        req["amount"], "Completed", reason
    )
    save_data()
    return True

@bot.callback_query_handler(func=lambda call: call.data == "card_withdraw_start")
def card_withdraw_start(call):
    data = get_user_data(call.from_user.id, username=call.from_user.username)
    card = _card_defaults(data)
    if card.get("status") != "ACTIVE":
        bot.answer_callback_query(call.id, "Card is not active.", show_alert=True)
        return
    if not card.get("pin_set"):
        bot.answer_callback_query(call.id, "Set your card PIN first.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = send_card_temp_message(call.message.chat.id, "💸 Enter withdrawal amount:")
    bot.register_next_step_handler(msg, card_withdraw_amount_step)

def card_withdraw_amount_step(message):
    try:
        amount = float((message.text or "").strip())
    except ValueError:
        send_card_temp_message(message.chat.id, "❌ Invalid amount.")
        return
    data = get_user_data(message.from_user.id, username=message.from_user.username)
    ok, reason = card_can_withdraw(data, amount)
    if not ok:
        send_card_temp_message(message.chat.id, f"❌ {reason}")
        return
    msg = send_card_temp_message(message.chat.id, "🔐 Enter your 4-digit card PIN:")
    bot.register_next_step_handler(msg, lambda m: card_withdraw_pin_step(m, amount))

def card_withdraw_pin_step(message, amount):
    uid = message.from_user.id
    pin = (message.text or "").strip()
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    data = get_user_data(uid, username=message.from_user.username)
    card = _card_defaults(data)
    if card.get("status") != "ACTIVE":
        send_card_temp_message(message.chat.id, '🔒 ' + tr(message.from_user.id, 'frozen_withdraw'))
        return
    if card.get("admin_frozen") or card.get("status") != "ACTIVE":
        send_card_temp_message(message.chat.id, "🔒 Card is frozen. Withdrawals are disabled until the administrator unfreezes the card.")
        return
    if card.get("locked"):
        send_card_temp_message(message.chat.id, "🔒 Card is locked. Contact support.")
        return
    if card.get("pin_hash") != _hash_card_secret(pin):
        card["failed_reveals"] = int(card.get("failed_reveals", 0)) + 1
        if card["failed_reveals"] >= 5:
            card["locked"] = True
        save_data()
        send_card_temp_message(
            message.chat.id,
            "🔒 Card locked." if card.get("locked") else "❌ Incorrect PIN."
        )
        return
    card["failed_reveals"] = 0
    save_data()
    msg = send_card_temp_message(message.chat.id, "📍 Enter withdrawal destination/wallet:")
    bot.register_next_step_handler(msg, lambda m: card_withdraw_destination_step(m, amount))

def card_withdraw_destination_step(message, amount):
    destination = (message.text or "").strip()
    if len(destination) < 4:
        send_card_temp_message(message.chat.id, "❌ Invalid destination.")
        return
    ok, reason, request_id = card_withdrawal_prepare(
        message.from_user.id, amount, destination
    )
    if not ok:
        send_card_temp_message(message.chat.id, f"❌ {reason}")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Confirm", callback_data=f"card_wd_confirm_{request_id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data=f"card_wd_cancel_{request_id}")
    )
    send_card_temp_message(
        message.chat.id,
        f"💳 *CARD WITHDRAWAL*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Amount: `${float(amount):.2f}`\n"
        f"📍 Destination: `{destination}`\n"
        f"🆔 Request: `{request_id}`\n\n"
        "Your balance is reserved until the request is completed or rejected.",
        parse_mode="Markdown", reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("card_wd_confirm_"))
def card_withdraw_confirm(call):
    request_id = call.data.replace("card_wd_confirm_", "")
    req = pending_withdrawals.get(request_id)
    if not req or req.get("user_id") != call.from_user.id:
        bot.answer_callback_query(call.id, "Request expired.", show_alert=True)
        return

    # Final authorization check: admin freeze always wins, even if the
    # withdrawal was started before the card was frozen.
    latest_data = get_user_data(call.from_user.id, username=call.from_user.username)
    latest_card = _card_defaults(latest_data)
    if latest_card.get("admin_frozen") or latest_card.get("status") != "ACTIVE" or latest_card.get("locked") or not latest_card.get("pin_set"):
        card_withdrawal_cancel(request_id)
        bot.answer_callback_query(call.id, "Card is frozen. Withdrawal cancelled and balance refunded.", show_alert=True)
        return

    bot.answer_callback_query(call.id, "Confirmed.")
    try:
        bot.send_message(
            ADMIN_ID,
            f"💳 *CARD WITHDRAWAL PENDING*\n"
            f"User: `{req['user_id']}`\n"
            f"Amount: `${req['amount']:.2f}`\n"
            f"Destination: `{req['wallet']}`\n"
            f"Request: `{request_id}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("card_wd_cancel_"))
def card_withdraw_cancel_callback(call):
    request_id = call.data.replace("card_wd_cancel_", "")
    req = pending_withdrawals.get(request_id)
    if not req or req.get("user_id") != call.from_user.id:
        bot.answer_callback_query(call.id, "Request expired.", show_alert=True)
        return
    card_withdrawal_cancel(request_id)
    bot.answer_callback_query(call.id, "Cancelled.")
    send_card_temp_message(call.message.chat.id, "↩️ Cancelled and balance refunded.")

# ================= ADMIN BALANCE / ACCOUNT / CARD PIN =================
def _admin_search_and_select(message, prefix):
    matches = search_users_by_query((message.text or "").strip())
    if not matches:
        bot.send_message(message.chat.id, "❌ No matching user found.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for uid, udata in matches:
        markup.add(types.InlineKeyboardButton(
            f"👤 {uid} | @{udata.get('username','N/A')}",
            callback_data=f"{prefix}_{uid}"
        ))
    bot.send_message(message.chat.id, "Select user:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_balance")
def admin_balance_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter username or User ID:")
    bot.register_next_step_handler(msg, lambda m: _admin_search_and_select(m, "adm_bal_user"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_bal_user_"))
def admin_balance_selected(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_bal_user_", ""))
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter `+amount reason` or `-amount reason`:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: admin_balance_apply(m, uid))

def admin_balance_apply(message, target_id):
    if message.from_user.id != ADMIN_ID: return
    parts = (message.text or "").strip().split(maxsplit=1)
    if not parts:
        bot.send_message(message.chat.id, "❌ Invalid adjustment."); return
    try:
        amount = float(parts[0])
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount."); return
    reason = parts[1] if len(parts) > 1 else "Admin adjustment"
    if admin_adjust_balance(target_id, amount, reason):
        bot.send_message(message.chat.id, f"✅ Balance adjusted by `${amount:+.2f}`.", parse_mode="Markdown")
        try: bot.send_message(target_id, f"💳 Balance adjustment: `${amount:+.2f}`\nReason: {reason}")
        except Exception: pass
    else:
        bot.send_message(message.chat.id, "❌ Adjustment rejected.")

@bot.callback_query_handler(func=lambda call: call.data == "adm_delete_user")
def admin_delete_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter username or User ID:")
    bot.register_next_step_handler(msg, lambda m: _admin_search_and_select(m, "adm_del_user"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_user_"))
def admin_delete_confirm(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_del_user_", ""))
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚠️ DELETE", callback_data=f"adm_del_confirm_{uid}"),
        types.InlineKeyboardButton("Cancel", callback_data="adm_delete_cancel")
    )
    bot.send_message(call.message.chat.id, f"Delete local account `{uid}` permanently?", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_confirm_"))
def admin_delete_execute(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_del_confirm_", ""))
    if uid == ADMIN_ID:
        bot.answer_callback_query(call.id, "Admin account cannot be deleted.", show_alert=True); return
    users.pop(uid, None)
    for key in list(pending_withdrawals):
        if pending_withdrawals[key].get("user_id") == uid: pending_withdrawals.pop(key, None)
    for key in list(pending_deposits):
        if pending_deposits[key].get("user_id") == uid: pending_deposits.pop(key, None)
    save_data()
    bot.answer_callback_query(call.id, "Deleted")
    bot.send_message(call.message.chat.id, f"✅ Account `{uid}` deleted.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "adm_delete_cancel")
def admin_delete_cancel(call):
    bot.answer_callback_query(call.id, "Cancelled")

@bot.callback_query_handler(func=lambda call: call.data == "adm_card_pin")
def admin_card_pin_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter username or User ID:")
    bot.register_next_step_handler(msg, lambda m: _admin_search_and_select(m, "adm_cardpin_user"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cardpin_user_"))
def admin_card_pin_selected(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_cardpin_user_", ""))
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter new 4-digit PIN:")
    bot.register_next_step_handler(msg, lambda m: admin_card_pin_apply(m, uid))

def admin_card_pin_apply(message, target_id):
    if message.from_user.id != ADMIN_ID: return
    pin = (message.text or "").strip()
    try: bot.delete_message(message.chat.id, message.message_id)
    except Exception: pass
    data = get_user_data(target_id)
    card = _card_defaults(data)
    if card.get("status") == "NOT_ISSUED":
        issue_virtual_card(target_id)
    if set_virtual_card_pin(target_id, pin, admin_override=True):
        card = _card_defaults(get_user_data(target_id))
        card["failed_reveals"] = 0
        card["locked"] = False
        save_data()
        bot.send_message(message.chat.id, f"✅ Card PIN changed for `{target_id}`.", parse_mode="Markdown")
        try: bot.send_message(target_id, "🔐 Your virtual card PIN was changed by administration.")
        except Exception: pass
    else:
        bot.send_message(message.chat.id, "❌ PIN must contain exactly 4 digits.")



# ================= ADVANCED VIRTUAL CARD CONTROLS =================
def freeze_virtual_card(user_id, reason="User requested"):
    data = get_user_data(user_id)
    card = _card_defaults(data)
    if card.get("status") != "ACTIVE":
        return False
    card["status"] = "FROZEN"
    card["admin_frozen"] = True
    card["freeze_reason"] = reason

    # Freeze is an immediate withdrawal block. Cancel all pending card
    # withdrawals and refund any balance reserved by those requests.
    for request_id, req in list(pending_withdrawals.items()):
        if req.get("user_id") == user_id and req.get("method") == "VIRTUAL_CARD":
            pending_withdrawals.pop(request_id, None)
            data["balance"] += float(req.get("amount", 0.0))

    save_data()
    return True

def unfreeze_virtual_card(user_id):
    data = get_user_data(user_id)
    card = _card_defaults(data)
    if card.get("status") != "FROZEN":
        return False
    card["status"] = "ACTIVE"
    card["admin_frozen"] = False
    card["freeze_reason"] = ""
    save_data()
    return True

def replace_virtual_card(user_id):
    """Replace card number/expiry while permanently preserving the existing CVC."""
    data = get_user_data(user_id)
    card = _card_defaults(data)
    was_admin_frozen = bool(card.get("admin_frozen") or card.get("status") == "FROZEN")

    # Preserve the existing CVC forever. Only generate it once if this is
    # a legacy card that never had a recoverable encrypted CVC.
    preserved_cvc_hash = card.get("cvc_hash", "")
    preserved_cvc_encrypted = card.get("cvc_encrypted", "")
    first_cvc = None

    if not preserved_cvc_encrypted:
        # Legacy cards cannot have their old CVC reconstructed from a hash.
        # Keep the old hash if present; otherwise issue one permanent CVC now.
        if not preserved_cvc_hash:
            first_cvc = "".join(str(secrets.randbelow(10)) for _ in range(3))
            preserved_cvc_hash = _hash_card_secret(first_cvc)
            preserved_cvc_encrypted = _encrypt_card_cvc(first_cvc)

    card["number"] = "9" + "".join(str(secrets.randbelow(10)) for _ in range(15))
    card["expiry"] = (datetime.now() + timedelta(days=365*3)).strftime("%m/%y")
    card["cvc_hash"] = preserved_cvc_hash
    card["cvc_encrypted"] = preserved_cvc_encrypted
    card["status"] = "FROZEN" if was_admin_frozen else "ACTIVE"
    card["admin_frozen"] = was_admin_frozen
    card["pin_hash"] = ""
    card["pin_set"] = False
    card["failed_reveals"] = 0
    card["locked"] = False
    card["daily_used"] = 0.0
    card["created_at"] = get_current_time()
    save_data()
    return card, first_cvc

def card_can_withdraw(data, amount):
    card = _card_defaults(data)
    if card.get("admin_frozen") or card.get("status") != "ACTIVE" or not card.get("pin_set") or card.get("locked"):
        return False, 'Your card is frozen. Withdrawals are disabled until the administrator unfreezes the card.' if card.get('status') == 'FROZEN' else 'Card is not ready for withdrawal.'
    amount = float(amount)
    daily_limit = float(card.get("daily_limit", 500.0))
    daily_used = float(card.get("daily_used", 0.0))
    if amount <= 0:
        return False, "Invalid amount."
    if amount > daily_limit or daily_used + amount > daily_limit:
        return False, f"Card daily limit is ${daily_limit:.2f}."
    return True, ""

def record_card_withdrawal(data, amount):
    card = _card_defaults(data)
    card["daily_used"] = float(card.get("daily_used", 0.0)) + float(amount)
    save_data()

def reset_card_daily_usage():
    for data in users.values():
        card = _card_defaults(data)
        card["daily_used"] = 0.0
    save_data()


@bot.callback_query_handler(func=lambda call: call.data == "adm_card_freeze")
def admin_card_freeze_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter username or User ID:")
    bot.register_next_step_handler(msg, lambda m: _admin_search_and_select(m, "adm_cardfreeze_user"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cardfreeze_user_"))
def admin_card_freeze_selected(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_cardfreeze_user_", ""))
    data = get_user_data(uid)
    card = _card_defaults(data)
    if not card.get("admin_frozen") and card.get("status") == "ACTIVE":
        if freeze_virtual_card(uid, "Admin action"):
            bot.answer_callback_query(call.id, "Card frozen.")
            try:
                bot.send_message(uid, "🔒 Your virtual card has been frozen by administration. Withdrawals and user PIN changes are disabled until the card is unfrozen.")
            except Exception:
                pass
    elif card.get("admin_frozen") or card.get("status") == "FROZEN":
        if unfreeze_virtual_card(uid):
            bot.answer_callback_query(call.id, "Card unfrozen.")
            try:
                bot.send_message(uid, "🔓 Your virtual card has been unfrozen by administration. Withdrawals and user PIN changes are available again.")
            except Exception:
                pass
    else:
        bot.answer_callback_query(call.id, "Card is not active.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "adm_card_replace")
def admin_card_replace_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Enter username or User ID:")
    bot.register_next_step_handler(msg, lambda m: _admin_search_and_select(m, "adm_cardreplace_user"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cardreplace_user_"))
def admin_card_replace_selected(call):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.replace("adm_cardreplace_user_", ""))
    new_card, _ = replace_virtual_card(uid)
    bot.answer_callback_query(call.id, "Card replaced.")
    bot.send_message(call.message.chat.id, f"✅ Card replaced for `{uid}`.", parse_mode="Markdown")
    try:
        bot.send_message(uid, "♻️ Your card was replaced by administration. Your CVC remains unchanged; please set a new PIN.")
    except Exception:
        pass

# --- WITHDRAWAL FLOW VIA REGISTERED PASSWORD ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_quick_"))
def handle_withdraw_quick(call):
    val = call.data.replace("wd_quick_", "")
    bot.answer_callback_query(call.id)
    
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    
    if val == "custom":
        msg = bot.send_message(call.message.chat.id, f"📤 Please submit custom withdrawal amount (Minimum `${MIN_WITHDRAW:.2f}`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_withdrawal_amount_text)
    else:
        amount = float(val)
        prompt_withdrawal_password(call.message.chat.id, amount)

def process_withdrawal_amount_text(message):
    try:
        amount = float(message.text.strip())
        prompt_withdrawal_password(message.chat.id, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid numeric format.")

def prompt_withdrawal_password(chat_id, amount, method_id=None):
    data=get_user_data(chat_id)
    card=_card_defaults(data)
    if amount < MIN_WITHDRAW:
        send_temp_message(chat_id,f"❌ Minimum withdrawal is `${MIN_WITHDRAW:.2f}`."); return
    if amount > data.get('balance',0.0):
        send_temp_message(chat_id,"❌ Insufficient portfolio balance."); return
    if card.get('status')!='ACTIVE' or not card.get('pin_set') or card.get('locked'):
        send_temp_message(chat_id,"❌ Your card must be active and have an unlocked PIN before withdrawal."); return
    # --- payout method routing (admin-managed payment methods) ---
    _methods = enabled_payment_methods()
    _custom = [x for x in _methods if x[0] != DEFAULT_METHOD_ID]
    if method_id is None and _custom:
        if len(_methods) > 1:
            show_withdraw_method_chooser(chat_id, amount, _methods); return
        method_id = _methods[0][0]
    elif method_id is None and not _methods:
        send_temp_message(chat_id, PM_NONE_ENABLED_TEXT); return
    if method_id and method_id != DEFAULT_METHOD_ID:
        prompt_custom_method_withdrawal(chat_id, amount, method_id, data); return
    if method_id == DEFAULT_METHOD_ID:
        if not any(x[0] == DEFAULT_METHOD_ID for x in _methods):
            send_temp_message(chat_id, "❌ This payout method is currently unavailable."); return
        if not is_valid_trc20(data.get('wallet')):
            send_temp_message(chat_id, "❌ Please register a valid TRC20 wallet via '⚙️ Account Settings' first."); return
    _usdt_fee_on = get_payment_methods()[DEFAULT_METHOD_ID].get('fee_enabled', True)
    if _usdt_fee_on:
        fee=withdrawal_fee_summary(amount)
    else:
        fee={'fee_trx':0.0,'trx_price':0.0,'fee_usd':0.0,'net_amount':round(float(amount),6)}
    if not fee:
        send_temp_message(chat_id,"⚠️ Live TRX price is temporarily unavailable. Please try again."); return
    if fee['net_amount'] <= 0:
        send_temp_message(chat_id,"❌ Withdrawal amount is too small after the 1.5 TRX network fee."); return
    cid=f"WD{uuid.uuid4().hex[:18].upper()}"
    pending_withdrawal_confirmations[cid]={'user_id':chat_id,'amount':float(amount),'fee':fee,'created_at':time.time()}
    save_data()
    markup=types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Confirm", callback_data=f"wd_fee_confirm_{cid}"),types.InlineKeyboardButton("❌ Cancel", callback_data=f"wd_fee_cancel_{cid}"))
    if not _usdt_fee_on:
        send_temp_message(chat_id,f"📤 *WITHDRAWAL CONFIRMATION*\n━━━━━━━━━━━━━━━━━━━━\n💰 Requested Amount: `${amount:.2f}`\n💸 Withdrawal Fee: `NO FEE`\n💵 *Final Amount You Receive:* `${fee['net_amount']:.6f}`\n💳 Destination: `{mask_wallet(data.get('wallet','Not Set'))}`\n\nConfirm to continue to Card PIN authentication.",reply_markup=markup,delay=45)
        return
    send_temp_message(chat_id,f"📤 *WITHDRAWAL FEE & CONFIRMATION*\n━━━━━━━━━━━━━━━━━━━━\n💰 Requested Amount: `${amount:.2f}`\n🪙 Live TRX Price: `${fee['trx_price']:.6f}`\n💸 Network Fee: `{fee['fee_trx']:.1f} TRX` = `${fee['fee_usd']:.6f}`\n💵 *Final Amount You Receive:* `${fee['net_amount']:.6f}`\n💳 Destination: `{mask_wallet(data.get('wallet','Not Set'))}`\n\nThe fee is calculated from the current online TRX price. Confirm to continue to Card PIN authentication.",reply_markup=markup,delay=45)

@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_fee_confirm_"))
def confirm_withdrawal_fee(call):
    cid=call.data.replace("wd_fee_confirm_","")
    req=pending_withdrawal_confirmations.pop(cid,None)
    if not req or req['user_id']!=call.from_user.id or time.time()-req['created_at']>45:
        bot.answer_callback_query(call.id,"Confirmation expired.",show_alert=True); return
    save_data(); bot.answer_callback_query(call.id,"Fee confirmed.")
    msg=send_temp_message(call.message.chat.id,"🔐 Enter your 4-digit Card PIN. Your PIN message will be deleted immediately.",delay=45)
    bot.register_next_step_handler(msg, verify_withdrawal_card_pin, req['amount'], req['fee'])

@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_fee_cancel_"))
def cancel_withdrawal_fee(call):
    cid=call.data.replace("wd_fee_cancel_","")
    req=pending_withdrawal_confirmations.pop(cid,None)
    if req and req['user_id']==call.from_user.id:
        save_data(); bot.answer_callback_query(call.id,"Cancelled."); send_temp_message(call.message.chat.id,"❌ Withdrawal cancelled. No balance was deducted.")
    else:
        bot.answer_callback_query(call.id,"Confirmation expired.",show_alert=True)

def verify_withdrawal_card_pin(message, amount, fee=None):
    user_id = message.from_user.id
    input_pin = message.text.strip() if message.text else ""
    delete_user_secret_message(message)
    data = get_user_data(user_id, username=message.from_user.username)
    card = _card_defaults(data)

    if card.get("locked"):
        send_temp_message(message.chat.id, "🔒 Card PIN is locked. Contact support.", delay=45)
        return
    if card.get("pin_hash") != _hash_card_secret(input_pin):
        card["failed_reveals"] = int(card.get("failed_reveals", 0)) + 1
        if card["failed_reveals"] >= 5:
            card["locked"] = True
        save_data()
        send_temp_message(
            message.chat.id,
            "🔒 Card locked after 5 incorrect PIN attempts." if card.get("locked")
            else "❌ Incorrect Card PIN.", delay=45
        )
        return

    card["failed_reveals"] = 0
    save_data()
    show_100_percent_loading(message.chat.id, "PROCESSING CARD PIN AUTHORIZATION")
    execute_user_withdrawal(message.chat.id, message.from_user, amount, fee)

def execute_user_withdrawal(chat_id, user_obj, amount, fee=None):
    user_id = user_obj.id
    username = f"@{user_obj.username}" if user_obj.username else "No Username"
    data = get_user_data(user_id, username=user_obj.username)
    card = _card_defaults(data)
    if card.get('status') != 'ACTIVE' or not card.get('pin_set') or card.get('locked'):
        send_temp_message(chat_id, '🔒 Your card is frozen. Withdrawals are disabled until the administrator unfreezes the card.')
        return

    # Payout destination: built-in USDT TRC20 wallet (original) or the user's saved account for an admin-added method.
    _mid = (fee or {}).get('method_id')
    _is_custom = bool(_mid and _mid != DEFAULT_METHOD_ID)
    if _is_custom:
        _pm = get_payment_methods().get(_mid)
        _acc = data.get('payment_accounts', {}).get(_mid, {}).get('account')
        if not _pm or not _pm.get('enabled', True) or not _acc:
            send_temp_message(chat_id, "❌ This payout method is no longer available or your account is not set. No balance was deducted.")
            return
        _dest, _method_name = _acc, _pm['name']
    else:
        _dest, _method_name = data['wallet'], None

    if data.get('withdrawal_permissions', 0) > 0:
        data['withdrawal_permissions'] -= 1

    data['balance'] -= amount
    data['withdrawal_timestamps'].append(datetime.now().timestamp())
    tx = add_transaction(user_id, "Withdrawal", amount, "Pending Audit", f"TRC20 Wallet: {mask_wallet(data['wallet'])}" if not _is_custom else f"{_method_name} Account: {mask_wallet(_dest)}")

    wd_id = f"W{int(datetime.now().timestamp())}{user_id % 1000}"
    
    pending_withdrawals[wd_id] = {
        'user_id': user_id,
        'amount': amount,
        'wallet': _dest,
        'timestamp': datetime.now().timestamp(),
        'admin_msg_id': None,
        'fee_trx': (fee or {}).get('fee_trx', 0.0),
        'trx_price': (fee or {}).get('trx_price', 0.0),
        'fee_usd': (fee or {}).get('fee_usd', 0.0),
        'net_payout': (fee or {}).get('net_amount', amount)
    }
    if _is_custom:
        pending_withdrawals[wd_id]['method_id'] = _mid
        pending_withdrawals[wd_id]['method_name'] = _method_name
    save_data()

    bot.send_message(
        chat_id,
        f"✅ *Withdrawal Requested Successfully!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 *REF ID:* `{tx['tx_id']}`\n"
        f"💵 *REQUESTED:* `${amount:.2f}`\n"
        f"💸 *FEE:* {_fee_text(fee)}\n"
        f"💰 *NET PAYOUT:* `${(fee or {}).get('net_amount',amount):.6f}`\n"
        + (f"💳 *TARGET TRC20 WALLET:* `{mask_wallet(data['wallet'])}`\n" if not _is_custom else f"💳 *TARGET {pm_escape(_method_name.upper())} ACCOUNT:* `{mask_wallet(_dest).replace(chr(96), '')}`\n") +
        f"📅 *TIMESTAMP:* `{get_current_time()}`\n\n"
        "Executing security audit... (Auto-reverses if unaddressed for 15 mins)",
        parse_mode="Markdown"
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_approve = types.InlineKeyboardButton("✅ Approve & Pay", callback_data=f"wd_app_{wd_id}")
    btn_reject = types.InlineKeyboardButton("❌ Reject", callback_data=f"wd_rej_menu_{wd_id}")
    markup.add(btn_approve, btn_reject)

    # Admin withdrawal request includes username, Telegram ID and wallet address.
    udata_info = get_user_data(user_id)
    admin_msg = (
        f"🚨 *NEW WITHDRAWAL REQUEST*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *USER ID:* `{user_id}`\n"
        f"🏷 *TELEGRAM USERNAME:* {username}\n"
        f"🆔 *TELEGRAM USER ID:* `{user_id}`\n"
        + (f"💳 *USER WALLET ADDRESS:* `{udata_info.get('wallet', 'Not Set')}`\n" if not _is_custom else f"💱 *PAYMENT METHOD:* {pm_escape(_method_name)}\n💳 *USER {pm_escape(_method_name.upper())} ACCOUNT:* `{str(_dest).replace(chr(96), '')}`\n") +
        f"💵 *REQUESTED:* `${amount:.2f}`\n"
        f"💸 *FEE:* {_fee_text(fee)}\n"
        f"💰 *NET PAYOUT:* `${(fee or {}).get('net_amount',amount):.6f}`\n"
        f"📅 *TIME:* `{get_current_time()}`\n"
        f"⏱ *REFUND TIMER:* 15-Minute Auto-Reversal Active\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        sent_admin_msg = bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", reply_markup=markup)
        if wd_id in pending_withdrawals:
            pending_withdrawals[wd_id]['admin_msg_id'] = sent_admin_msg.message_id
            save_data()
    except Exception as e:
        print(f"Failed to send admin withdrawal notification: {e}")

# --- INVESTMENT EXECUTION (STARTER & PRO RULES) ---
@bot.callback_query_handler(func=lambda call: call.data in ("invest_starter", "invest_vip"))
def process_investment_plan(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    plan_type = "Starter Plan (5%)" if call.data == "invest_starter" else "VIP Pro Plan (7%)"
    
    if call.data == "invest_starter":
        text = "🚀 *STARTER PLAN DEPLOYMENT*\nLimits: **$10.00 – $500.00**\nSubmit USDT amount to invest from active balance:"
    else:
        text = "💎 *VIP PRO PLAN DEPLOYMENT*\nLimits: **$501.00 – Unlimited**\nSubmit USDT amount to invest from active balance:"

    msg = bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, execute_investment, plan_type)

def execute_investment(message, plan_type):
    user_id = message.from_user.id
    data = get_user_data(user_id, username=message.from_user.username)
    try:
        amount = float(message.text.strip())
    except ValueError:
        send_temp_message(message.chat.id, "❌ Invalid numeric format.")
        return
    if amount <= 0:
        send_temp_message(message.chat.id, "❌ Investment amount must be greater than zero.")
        return
    if "Starter" in plan_type and not (10.0 <= amount <= 500.0):
        send_temp_message(message.chat.id, "❌ Starter Plan accepts $10.00–$500.00.")
        return
    if "VIP Pro" in plan_type and amount < 501.0:
        send_temp_message(message.chat.id, "❌ VIP Pro Plan requires a minimum of $501.00.")
        return
    if amount > data.get('balance', 0.0):
        send_temp_message(message.chat.id, "❌ Insufficient available balance.")
        return
    confirm_id=f"INV{uuid.uuid4().hex[:18].upper()}"
    pending_investment_confirmations[confirm_id]={'user_id':user_id,'amount':amount,'plan':plan_type,'created_at':time.time()}
    save_data()
    markup=types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Confirm", callback_data=f"invest_confirm_{confirm_id}"), types.InlineKeyboardButton("❌ Cancel", callback_data=f"invest_cancel_{confirm_id}"))
    roi=0.05 if "Starter" in plan_type else 0.07
    profit=round(amount*roi,2)
    send_temp_message(message.chat.id, f"📈 *INVESTMENT CONFIRMATION*\n━━━━━━━━━━━━━━━━━━━━\n📦 Plan: `{plan_type}`\n💰 Amount: `${amount:.2f}`\n📈 Estimated 24H Profit: `+${profit:.2f}`\n💵 Balance After Investment: `${data['balance']-amount:.2f}`\n\nConfirm or cancel this investment.", reply_markup=markup, delay=30)

@bot.callback_query_handler(func=lambda call: call.data.startswith("invest_confirm_"))
def confirm_investment(call):
    cid=call.data.replace("invest_confirm_","")
    req=pending_investment_confirmations.pop(cid,None)
    if not req or req['user_id']!=call.from_user.id or time.time()-req['created_at']>30:
        bot.answer_callback_query(call.id,"Investment confirmation expired.",show_alert=True); return
    data=get_user_data(call.from_user.id, username=call.from_user.username)
    amount=float(req['amount'])
    if amount>data.get('balance',0.0):
        bot.answer_callback_query(call.id,"Insufficient balance.",show_alert=True); return
    data['balance']=round(data['balance']-amount,2)
    data['total_invested']=round(data.get('total_invested',0.0)+amount,2)
    data['last_investment_timestamp']=time.time()
    data.setdefault('active_plans',[]).append({'plan':req['plan'],'amount':amount,'date':get_current_time(),'timestamp':time.time(),'roi':0.05 if 'Starter' in req['plan'] else 0.07})
    add_transaction(call.from_user.id,"Investment",amount,"Completed",f"Plan: {req['plan']}")
    save_data()
    bot.answer_callback_query(call.id,"Investment confirmed.")
    send_temp_message(call.message.chat.id,f"✅ *INVESTMENT CONFIRMED*\n\n📦 Plan: `{req['plan']}`\n💰 Amount: `${amount:.2f}`\n⏱️ Maturity: `24 Hours`\n💵 Remaining Balance: `${data['balance']:.2f}`")
    send_premium_telegram_notification(call.from_user.id,"Investment","INVESTMENT DEPLOYED SUCCESSFULLY",amount_text=f"${amount:.2f}",balance_text=f"${data['balance']:.2f}",status="COMPLETED",details=f"📦 *PLAN:* `{req['plan']}`\\n⏱️ *MATURITY:* `24 Hours`")

@bot.callback_query_handler(func=lambda call: call.data.startswith("invest_cancel_"))
def cancel_investment_confirmation(call):
    cid=call.data.replace("invest_cancel_","")
    req=pending_investment_confirmations.pop(cid,None)
    if req and req['user_id']==call.from_user.id:
        save_data(); bot.answer_callback_query(call.id,"Cancelled.")
        send_temp_message(call.message.chat.id,"❌ Investment cancelled. No balance was deducted.")
    else:
        bot.answer_callback_query(call.id,"Confirmation expired.",show_alert=True)

# ================= ADMIN ACTIONS =================

# DEPOSIT APPROVAL
@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_app_"))
def admin_dep_approve_execute(call):
    if call.from_user.id != ADMIN_ID:
        return
    dep_id = call.data.replace("dep_app_", "")

    if dep_id not in pending_deposits:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    req = pending_deposits.pop(dep_id, None)
    if not req:
        return

    target_id = req['user_id']
    amount = req['amount']
    txid = req['txid']
    if req.get('txid_key'):
        used_txids.add(req['txid_key'])

    data = get_user_data(target_id)
    data['balance'] += amount
    data['total_deposited'] += amount
    add_transaction(target_id, "Deposit", amount, "Completed", f"TxID: {mask_txid(txid)}")

    if data['referred_by']:
        ref_id = data['referred_by']
        ref_data = get_user_data(ref_id)
        commission = amount * 0.01
        ref_data['balance'] += commission
        ref_data['referral_earnings'] += commission
        add_transaction(ref_id, "Referral Commission", commission, "Completed", f"Partner ID: {mask_id(target_id)}")
        try:
            bot.send_message(ref_id, f"🎁 *1% Referral Commission Received!* (`+${commission:.2f}`)", parse_mode="Markdown")
        except Exception:
            pass

    save_data()
    bot.answer_callback_query(call.id, "✅ Deposit Approved Successfully!")

    try:
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

    bot.send_message(target_id, f"🎉 *Deposit Approved!*\n`${amount:.2f}` has been credited to your account balance.", parse_mode="Markdown")
    post_channel_deposit_success(target_id, amount, txid)
    show_celebration_effect(target_id)

# DEPOSIT REJECT MENU
@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_rej_menu_"))
def admin_dep_reject_menu(call):
    if call.from_user.id != ADMIN_ID:
        return
    dep_id = call.data.replace("dep_rej_menu_", "")

    if dep_id not in pending_deposits:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    b1 = types.InlineKeyboardButton("❌ 1. Invalid Transaction Hash (TxID)", callback_data=f"dep_rej_do_{dep_id}_1")
    b2 = types.InlineKeyboardButton("❌ 2. Incorrect Capital Amount Received", callback_data=f"dep_rej_do_{dep_id}_2")
    b3 = types.InlineKeyboardButton("❌ 3. Invalid Screenshot Audit Proof", callback_data=f"dep_rej_do_{dep_id}_3")
    markup.add(b1, b2, b3)

    try:
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + "\n\n❓ *Select Deposit Rejection Reason:*",
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception:
        pass

# DEPOSIT REJECT EXECUTION
@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_rej_do_"))
def admin_dep_reject_execute(call):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    dep_id = parts[3]
    reason_code = parts[4]

    if dep_id not in pending_deposits:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    req = pending_deposits.pop(dep_id, None)
    if not req:
        return

    target_id = req['user_id']
    amount = req['amount']

    reasons_map = {
        "1": "Invalid Transaction Hash (TxID)",
        "2": "Incorrect Capital Amount Received",
        "3": "Invalid or Unverifiable Screenshot Proof"
    }
    selected_reason = reasons_map.get(reason_code, "Security Audit Failed")

    show_100_percent_loading(target_id, "PROCESSING TRANSACTION REJECTION")

    data = get_user_data(target_id)
    add_transaction(target_id, "Deposit", amount, "Cancelled", f"Reason: {selected_reason}")
    save_data()
    bot.answer_callback_query(call.id, "❌ Deposit Cancelled!")

    try:
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

    bot.send_message(target_id, f"❌ *Deposit Rejected!*\nAmount: `${amount:.2f}`\nReason: `{selected_reason}`", parse_mode="Markdown")
    post_channel_transaction_cancelled(target_id, "Deposit", amount, selected_reason)

# WITHDRAWAL APPROVAL
@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_app_"))
def admin_wd_approve_execute(call):
    if call.from_user.id != ADMIN_ID:
        return
    wd_id = call.data.replace("wd_app_", "")

    if wd_id not in pending_withdrawals:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    req = pending_withdrawals.pop(wd_id, None)
    if not req:
        return

    target_id = req['user_id']
    amount = req['amount']
    net_payout = float(req.get('net_payout', amount))
    fee_usd = float(req.get('fee_usd', 0.0))
    wallet = req['wallet']

    data = get_user_data(target_id)
    data['total_withdrawn'] += net_payout
    data['total_fees'] = round(float(data.get('total_fees', 0.0)) + fee_usd, 6)
    _wd_mname = req.get('method_name')
    if _wd_mname:
        add_transaction(target_id, "Withdrawal", net_payout, "Completed", f"{_wd_mname} Account: {mask_wallet(wallet)} | Requested: ${amount:.2f} | Fee: ${fee_usd:.2f}")
    else:
        add_transaction(target_id, "Withdrawal", net_payout, "Completed", f"TRC20 Wallet: {mask_wallet(wallet)} | Requested: ${amount:.2f} | Fee: {req.get('fee_trx',0.0):.1f} TRX (${fee_usd:.6f})")
    save_data()

    bot.answer_callback_query(call.id, "✅ Withdrawal Approved & Paid!")

    try:
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

    if _wd_mname:
        bot.send_message(target_id, f"🎉 *Withdrawal Approved!*\n`${net_payout:.6f}` has been dispatched to your {pm_escape(_wd_mname)} account:\n`{str(wallet).replace(chr(96), '')}`", parse_mode="Markdown")
    else:
        bot.send_message(target_id, f"🎉 *Withdrawal Approved!*\n`${net_payout:.6f}` has been dispatched to your TRC20 destination wallet:\n`{wallet}`", parse_mode="Markdown")
    post_channel_withdraw_success(target_id, net_payout, wallet)
    show_celebration_effect(target_id)

# WITHDRAWAL REJECT MENU
@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_rej_menu_"))
def admin_wd_reject_menu(call):
    if call.from_user.id != ADMIN_ID:
        return
    wd_id = call.data.replace("wd_rej_menu_", "")

    if wd_id not in pending_withdrawals:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    _rej_label = "❌ 1. Invalid TRC20 Wallet Address" if not pending_withdrawals[wd_id].get('method_name') else "❌ 1. Invalid Account Number"
    b1 = types.InlineKeyboardButton(_rej_label, callback_data=f"wd_rej_do_{wd_id}_1")
    b2 = types.InlineKeyboardButton("❌ 2. Suspicious Account Activity", callback_data=f"wd_rej_do_{wd_id}_2")
    b3 = types.InlineKeyboardButton("❌ 3. Network Processing Error", callback_data=f"wd_rej_do_{wd_id}_3")
    markup.add(b1, b2, b3)

    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=call.message.text + "\n\n❓ *Select Withdrawal Rejection Reason:*",
            parse_mode="Markdown",
            reply_markup=markup
        )
    except Exception:
        pass

# WITHDRAWAL REJECT EXECUTION WITH REFUND
@bot.callback_query_handler(func=lambda call: call.data.startswith("wd_rej_do_"))
def admin_wd_reject_execute(call):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split("_")
    wd_id = parts[3]
    reason_code = parts[4]

    if wd_id not in pending_withdrawals:
        bot.answer_callback_query(call.id, "⚠️ Transaction already processed!", show_alert=True)
        return

    req = pending_withdrawals.pop(wd_id, None)
    if not req:
        return

    target_id = req['user_id']
    amount = req['amount']

    reasons_map = {
        "1": "Invalid TRC20 Wallet Address Provided" if not req.get('method_name') else "Invalid Payout Account Number Provided",
        "2": "Suspicious Account Activity Detected",
        "3": "Network Protocol Processing Error"
    }
    selected_reason = reasons_map.get(reason_code, "Security Audit Failed")

    show_100_percent_loading(target_id, "PROCESSING WITHDRAWAL REJECTION")

    data = get_user_data(target_id)
    data['balance'] += amount

    add_transaction(target_id, "Withdrawal", amount, "Cancelled", f"Reason: {selected_reason}")
    save_data()
    bot.answer_callback_query(call.id, "❌ Withdrawal Cancelled & Refunded!")

    try:
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

    bot.send_message(
        target_id, 
        f"❌ *Withdrawal Rejected!*\nAmount: `${amount:.2f}`\nReason: `{selected_reason}`\n\n💰 Funds have been successfully reinstated to your active balance.", 
        parse_mode="Markdown"
    )
    post_channel_transaction_cancelled(target_id, "Withdrawal", amount, selected_reason)


# --- PREMIUM TELEGRAM TRANSACTION NOTIFICATIONS ---
def send_premium_telegram_notification(
    user_id,
    event_type,
    title,
    amount_text=None,
    balance_text=None,
    status="COMPLETED",
    details=None
):
    """Unified premium Telegram notification for account transactions.
    Existing colors, business rules and callback logic remain unchanged.
    """
    try:
        event_upper = str(event_type).lower()
        event_key = 'security'
        if 'deposit' in event_upper: event_key = 'deposit'
        elif 'withdraw' in event_upper: event_key = 'withdrawal'
        elif 'referral' in event_upper: event_key = 'referral'
        elif 'invest' in event_upper or 'maturity' in event_upper: event_key = 'investment'
        if not notification_enabled(user_id, event_key):
            return
        status_upper = str(status).upper()
        status_icon = "✅"
        if any(x in status_upper for x in ("PENDING", "PROCESSING", "REVIEW")):
            status_icon = "⏳"
        elif any(x in status_upper for x in ("REJECT", "CANCEL", "FAILED", "DECLINED")):
            status_icon = "❌"
        elif "MATUR" in str(event_type).upper():
            status_icon = "🏆"
        elif "DEPOSIT" in str(event_type).upper():
            status_icon = "💳"
        elif "WITHDRAW" in str(event_type).upper():
            status_icon = "💸"
        elif "INVEST" in str(event_type).upper():
            status_icon = "📈"

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🏢 *{COMPANY_NAME}*",
            "🔐 *SECURE ACCOUNT NOTIFICATION*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{status_icon} *{title}*",
            "",
            f"🏷 *TYPE:* `{event_type}`",
            f"📊 *STATUS:* `{status}`",
        ]

        if amount_text is not None:
            lines.append(f"💰 *AMOUNT:* `{amount_text}`")
        if balance_text is not None:
            lines.append(f"💵 *AVAILABLE BALANCE:* `{balance_text}`")

        if details:
            lines.extend([
                "",
                "📝 *TRANSACTION DETAILS*",
                f"{details}"
            ])

        lines.extend([
            anti_phishing_suffix(user_id),
            f"🕒 *TIME:* `{get_current_time()}`",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🛡️ _This is an automated secure account notification._"
        ])

        bot.send_message(
            user_id,
            "\n".join(lines),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Premium Telegram Notification Exception: {e}")

# ================= PAYMENT METHODS (ADMIN-MANAGED DEPOSIT METHODS) =================
# Built-in method "usdt" = the original USDT TRC20 flow (auto blockchain check).
# Methods added by the admin (bKash, Nagad, Binance, bank, ...) use a manual flow:
# user pays -> sends Transaction ID/reference -> uploads screenshot -> admin approves.
DEFAULT_METHOD_ID = "usdt"
PM_NONE_ENABLED_TEXT = (
    "🚫 *DEPOSITS TEMPORARILY UNAVAILABLE*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "No payment method is currently active. Please try again later or contact support."
)

def pm_escape(text):
    """Escape Telegram legacy-Markdown special characters in admin-entered text."""
    return re.sub(r'([_*`\[])', r'\\\1', str(text))

def get_payment_methods():
    """Return the payment-method dict, making sure the built-in USDT method exists."""
    if DEFAULT_METHOD_ID not in payment_methods:
        fresh = {DEFAULT_METHOD_ID: {"name": "USDT (TRC20)", "builtin": True, "enabled": True}}
        fresh.update(payment_methods)
        payment_methods.clear()
        payment_methods.update(fresh)
    return payment_methods

def enabled_payment_methods():
    return [(mid, m) for mid, m in get_payment_methods().items() if m.get("enabled", True)]

def _pm_address(mid, m):
    return USDT_ADDRESS if mid == DEFAULT_METHOD_ID else m.get("address", "")

# ---------- USER SIDE ----------
def start_deposit_with_method(chat_id, amount):
    """Entry point after the amount is chosen. One active method -> go straight to it;
    several -> let the user choose."""
    methods = enabled_payment_methods()
    if not methods:
        bot.send_message(chat_id, PM_NONE_ENABLED_TEXT, parse_mode="Markdown")
        return
    if len(methods) == 1:
        begin_method_deposit(chat_id, amount, methods[0][0])
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for mid, m in methods:
        markup.add(types.InlineKeyboardButton(f"💳 {m['name']}", callback_data=f"dep_m_{mid}_{amount:.2f}"))
    bot.send_message(
        chat_id,
        "💱 *SELECT PAYMENT METHOD*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *CAPITAL AMOUNT:* `${amount:.2f}`\n\n"
        "Choose how you would like to pay:",
        parse_mode="Markdown", reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_m_"))
def handle_deposit_method_choice(call):
    try:
        mid, amt = call.data[len("dep_m_"):].rsplit("_", 1)
        amount = float(amt)
    except Exception:
        bot.answer_callback_query(call.id)
        return
    methods = get_payment_methods()
    if amount < MIN_DEPOSIT or mid not in methods or not methods[mid].get("enabled", True):
        bot.answer_callback_query(call.id, "This payment method is currently unavailable.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    begin_method_deposit(call.message.chat.id, amount, mid)

def begin_method_deposit(chat_id, amount, mid):
    if mid == DEFAULT_METHOD_ID:
        proceed_deposit_payment(chat_id, amount)   # original USDT TRC20 flow (unchanged)
        return
    m = get_payment_methods().get(mid)
    if not m:
        bot.send_message(chat_id, "❌ This payment method is no longer available.")
        return
    address = str(m.get("address", "")).replace("`", "")
    text = (
        f"📥 *DEPOSIT PAYMENT SPECIFICATION*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *CAPITAL AMOUNT:* `${amount:.2f}`\n"
        f"💳 *PAYMENT METHOD:* {pm_escape(m['name'])}\n\n"
        "🏦 *PAYMENT DETAILS*\n"
        "┌────────────────────────────────────────┐\n"
        f"│ `{address}`\n"
        "└────────────────────────────────────────┘\n"
        "📋 *Tap and hold the details above to copy.*\n"
    )
    if m.get("instructions"):
        text += f"\n📝 *INSTRUCTIONS*\n{pm_escape(m['instructions'])}\n"
    text += "\n⚠️ After paying, submit your **Transaction ID / Reference** below:"
    msg = bot.send_message(chat_id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_manual_deposit_ref, amount, mid)

def process_manual_deposit_ref(message, amount, mid):
    ref = (message.text or "").strip()
    m = get_payment_methods().get(mid)
    if not m or not m.get("enabled", True):
        bot.send_message(message.chat.id, "❌ This payment method is no longer available. Please start a new deposit.")
        return
    if len(ref) < 4 or len(ref) > 100 or ref.startswith("/"):
        msg = bot.send_message(
            message.chat.id,
            "🛑 *INVALID TRANSACTION ID / REFERENCE!*\nPlease submit the Transaction ID shown in your payment receipt:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_manual_deposit_ref, amount, mid)
        return
    key = f"{mid}:{ref.lower()}"
    if key in used_txids or any(r.get("txid_key") == key for r in pending_deposits.values()):
        bot.send_message(
            message.chat.id,
            "❌ *SECURITY AUDIT ERROR:* This Transaction ID has already been submitted.",
            parse_mode="Markdown"
        )
        return
    msg = bot.send_message(
        message.chat.id,
        f"📸 *DEPOSIT VERIFICATION REQUIRED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *Requested Amount:* `${amount:.2f}`\n"
        f"💳 *Method:* {pm_escape(m['name'])}\n"
        f"🔗 *Reference:* `{mask_txid(ref).replace(chr(96), '')}`\n\n"
        "Please upload a clear screenshot of the completed payment for *Manual Deposit Review*. "
        "The balance will remain unchanged until approval.",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_deposit_screenshot, amount, ref, mid)

# ---------- WITHDRAWAL SIDE (payout methods + per-method fee ON/OFF) ----------
def _fee_text(fee):
    """Fee line used in withdrawal messages. Built-in USDT keeps the original TRX format."""
    fee = fee or {}
    if float(fee.get('fee_trx', 0.0)) > 0:
        return f"`{fee.get('fee_trx', 0.0):.1f} TRX` = `${fee.get('fee_usd', 0.0):.6f}`"
    if float(fee.get('fee_usd', 0.0)) > 0:
        return f"`${fee.get('fee_usd', 0.0):.2f}`"
    return "`NO FEE`"

def _pm_fee_label(mid, m):
    """Human readable fee setting for the admin panel."""
    if mid == DEFAULT_METHOD_ID:
        return f"{TRX_WITHDRAWAL_FEE:.1f} TRX network fee (live price)"
    mode, val = m.get("fee_mode", "percent"), float(m.get("fee_value", 0.0) or 0.0)
    if val <= 0:
        return "not set"
    return f"{val:g}% of the amount" if mode == "percent" else f"${val:g} fixed"

def show_withdraw_method_chooser(chat_id, amount, methods):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for mid, m in methods:
        markup.add(types.InlineKeyboardButton(f"💳 {m['name']}", callback_data=f"wdm_{mid}_{amount:.2f}"))
    send_temp_message(
        chat_id,
        "💱 *SELECT PAYOUT METHOD*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 *WITHDRAWAL AMOUNT:* `${amount:.2f}`\n\n"
        "Choose where you would like to receive your payout:",
        reply_markup=markup, delay=60
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("wdm_"))
def handle_withdraw_method_choice(call):
    try:
        mid, amt = call.data[len("wdm_"):].rsplit("_", 1)
        amount = float(amt)
    except Exception:
        bot.answer_callback_query(call.id)
        return
    m = get_payment_methods().get(mid)
    if not m or not m.get("enabled", True):
        bot.answer_callback_query(call.id, "This payout method is currently unavailable.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    prompt_withdrawal_password(call.message.chat.id, amount, method_id=mid)

def prompt_custom_method_withdrawal(chat_id, amount, mid, data):
    """Confirmation step for a withdrawal through an admin-added payment method."""
    m = get_payment_methods().get(mid)
    if not m or not m.get("enabled", True):
        send_temp_message(chat_id, "❌ This payout method is currently unavailable."); return
    account = data.get('payment_accounts', {}).get(mid, {}).get('account')
    if not account:
        send_temp_message(
            chat_id,
            f"❌ *{pm_escape(m['name'])} account not set!*\nPlease save your account number via "
            "'⚙️ Account Settings → 💳 Wallet / Address Settings' first.")
        return
    fee_usd = 0.0
    if m.get("fee_enabled", False):
        val = float(m.get("fee_value", 0.0) or 0.0)
        fee_usd = round(amount * val / 100.0, 6) if m.get("fee_mode", "percent") == "percent" else round(val, 6)
    net = round(float(amount) - fee_usd, 6)
    if net <= 0:
        send_temp_message(chat_id, "❌ Withdrawal amount is too small after the withdrawal fee."); return
    fee = {'fee_trx': 0.0, 'trx_price': 0.0, 'fee_usd': fee_usd, 'net_amount': net,
           'method_id': mid, 'method_name': m['name']}
    cid = f"WD{uuid.uuid4().hex[:18].upper()}"
    pending_withdrawal_confirmations[cid] = {'user_id': chat_id, 'amount': float(amount), 'fee': fee, 'created_at': time.time()}
    save_data()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Confirm", callback_data=f"wd_fee_confirm_{cid}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data=f"wd_fee_cancel_{cid}"))
    send_temp_message(
        chat_id,
        f"📤 *WITHDRAWAL {'FEE & ' if fee_usd > 0 else ''}CONFIRMATION*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"💱 Payout Method: *{pm_escape(m['name'])}*\n"
        f"💰 Requested Amount: `${amount:.2f}`\n"
        f"💸 Withdrawal Fee: {_fee_text(fee)}\n"
        f"💵 *Final Amount You Receive:* `${net:.6f}`\n"
        f"💳 Destination: `{mask_wallet(str(account)).replace(chr(96), '')}`\n\n"
        "Confirm to continue to Card PIN authentication.",
        reply_markup=markup, delay=45)

# ---------- ADMIN: withdrawal fee ON/OFF per method ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_ft_"))
def admin_pm_fee_toggle(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_ft_"):]
    m = get_payment_methods().get(mid)
    if not m:
        bot.answer_callback_query(call.id, "Method not found.", show_alert=True); return
    default_on = (mid == DEFAULT_METHOD_ID)
    now_on = m.get("fee_enabled", default_on)
    if not now_on and mid != DEFAULT_METHOD_ID and float(m.get("fee_value", 0.0) or 0.0) <= 0:
        # Turning fee ON needs an amount first.
        bot.answer_callback_query(call.id)
        _admin_pm_ask_fee(call.message.chat.id, mid)
        return
    m["fee_enabled"] = not now_on
    save_data()
    bot.answer_callback_query(call.id, f"Withdrawal fee for {m['name']} is now {'ON' if m['fee_enabled'] else 'OFF'}")
    text, markup = _pm_detail_view(mid)
    _pm_show(call, text, markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_fs_"))
def admin_pm_fee_set_start(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_fs_"):]
    m = get_payment_methods().get(mid)
    if not m or m.get("builtin"):
        bot.answer_callback_query(call.id, "Cannot set a custom fee for this method.", show_alert=True); return
    bot.answer_callback_query(call.id)
    _admin_pm_ask_fee(call.message.chat.id, mid)

def _admin_pm_ask_fee(chat_id, mid):
    msg = bot.send_message(
        chat_id,
        "💸 *SET WITHDRAWAL FEE*\n\nSend the fee as a percentage, e.g. `2%` (of the withdrawal amount), "
        "or a fixed USD amount, e.g. `1.5`.\nSaving turns the fee ON. Send /cancel to abort.",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_pm_fee_set_apply, mid)

def admin_pm_fee_set_apply(message, mid):
    if message.from_user.id != ADMIN_ID: return
    t = _pm_admin_text(message)
    if t is None:
        bot.send_message(message.chat.id, "❎ Cancelled."); return
    mm = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(%?)", t.strip())
    if not mm or float(mm.group(1)) <= 0 or (mm.group(2) and float(mm.group(1)) > 50) or float(mm.group(1)) > 1000:
        msg = bot.send_message(message.chat.id, "❌ Invalid. Send like `2%` (max 50%) or a fixed USD amount like `1.5`:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, admin_pm_fee_set_apply, mid); return
    m = get_payment_methods().get(mid)
    if not m or m.get("builtin"):
        bot.send_message(message.chat.id, "❌ Method not found."); return
    m["fee_mode"] = "percent" if mm.group(2) else "fixed"
    m["fee_value"] = float(mm.group(1))
    m["fee_enabled"] = True
    save_data()
    text, markup = _pm_detail_view(mid)
    bot.send_message(message.chat.id, "✅ *Withdrawal fee saved and turned ON.*\n\n" + text, parse_mode="Markdown", reply_markup=markup)

# ---------- ADMIN SIDE ----------
def _pm_admin_text(message):
    """Text of an admin reply, or None if empty / a command (acts as cancel)."""
    t = (message.text or "").strip() if message.from_user.id == ADMIN_ID else ""
    if not t or t.startswith("/"):
        return None
    return t

def _pm_list_view():
    methods = get_payment_methods()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for mid, m in methods.items():
        icon = "✅" if m.get("enabled", True) else "⛔"
        markup.add(types.InlineKeyboardButton(f"{icon} {m['name']}", callback_data=f"adm_pm_v_{mid}"))
    markup.add(types.InlineKeyboardButton("➕ Add Payment Method", callback_data="adm_pm_add"))
    text = (
        "💱 *PAYMENT METHODS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ = ON (visible to users)   ⛔ = OFF (hidden)\n"
        "Tap a method to edit, turn ON/OFF or delete it."
    )
    return text, markup

def _pm_detail_view(mid):
    m = get_payment_methods().get(mid)
    if not m:
        return None, None
    on = m.get("enabled", True)
    builtin = bool(m.get("builtin"))
    addr = str(_pm_address(mid, m)).replace("`", "")
    text = (
        f"💱 *{pm_escape(m['name'])}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Status:* {'✅ ON' if on else '⛔ OFF'}\n"
        f"🧩 *Type:* {'Built-in (auto blockchain check, address from .env)' if builtin else 'Manual review by admin'}\n"
        f"🏦 *Details:* `{addr or 'Not set'}`\n"
    )
    if not builtin:
        text += f"📝 *Instructions:* {pm_escape(m.get('instructions') or 'None')}\n"
    fee_on = m.get("fee_enabled", builtin)
    text += f"💸 *Withdrawal Fee:* {'✅ ON' if fee_on else '⛔ OFF'} — {pm_escape(_pm_fee_label(mid, m))}\n"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("⛔ Turn OFF" if on else "✅ Turn ON", callback_data=f"adm_pm_t_{mid}"))
    markup.add(types.InlineKeyboardButton("💸 Withdrawal Fee: ON → Turn OFF" if fee_on else "💸 Withdrawal Fee: OFF → Turn ON", callback_data=f"adm_pm_ft_{mid}"))
    if not builtin:
        markup.add(types.InlineKeyboardButton("💸 Set Fee Amount", callback_data=f"adm_pm_fs_{mid}"))
        markup.add(
            types.InlineKeyboardButton("✏️ Edit Name", callback_data=f"adm_pm_e_name_{mid}"),
            types.InlineKeyboardButton("✏️ Edit Details", callback_data=f"adm_pm_e_addr_{mid}")
        )
        markup.add(
            types.InlineKeyboardButton("✏️ Edit Instructions", callback_data=f"adm_pm_e_ins_{mid}"),
            types.InlineKeyboardButton("🗑 Delete", callback_data=f"adm_pm_d_{mid}")
        )
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="adm_pm"))
    return text, markup

def _pm_show(call, text, markup):
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode="Markdown", reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_pm")
def admin_pm_list(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    text, markup = _pm_list_view()
    _pm_show(call, text, markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_v_"))
def admin_pm_view(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_v_"):]
    text, markup = _pm_detail_view(mid)
    if not text:
        bot.answer_callback_query(call.id, "Method not found.", show_alert=True); return
    bot.answer_callback_query(call.id)
    _pm_show(call, text, markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_t_"))
def admin_pm_toggle(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_t_"):]
    m = get_payment_methods().get(mid)
    if not m:
        bot.answer_callback_query(call.id, "Method not found.", show_alert=True); return
    m["enabled"] = not m.get("enabled", True)
    save_data()
    bot.answer_callback_query(call.id, f"{m['name']} is now {'ON' if m['enabled'] else 'OFF'}")
    text, markup = _pm_detail_view(mid)
    _pm_show(call, text, markup)

# --- add new method: name -> details -> instructions ---
@bot.callback_query_handler(func=lambda call: call.data == "adm_pm_add")
def admin_pm_add_start(call):
    if call.from_user.id != ADMIN_ID: return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "➕ *ADD PAYMENT METHOD* (1/3)\n\nEnter the *method name* (e.g. `bKash`, `Nagad`, `Binance Pay`).\nSend /cancel to abort.",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_pm_add_name)

def admin_pm_add_name(message):
    if message.from_user.id != ADMIN_ID: return
    name = _pm_admin_text(message)
    if name is None:
        bot.send_message(message.chat.id, "❎ Cancelled."); return
    if len(name) > 40:
        msg = bot.send_message(message.chat.id, "❌ Name is too long (max 40 characters). Enter the method name again:")
        bot.register_next_step_handler(msg, admin_pm_add_name); return
    msg = bot.send_message(
        message.chat.id,
        "➕ *ADD PAYMENT METHOD* (2/3)\n\nEnter the *account number / wallet address / payment details* users must send money to.\nSend /cancel to abort.",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_pm_add_details, name)

def admin_pm_add_details(message, name):
    if message.from_user.id != ADMIN_ID: return
    details = _pm_admin_text(message)
    if details is None:
        bot.send_message(message.chat.id, "❎ Cancelled."); return
    if len(details) > 200:
        msg = bot.send_message(message.chat.id, "❌ Too long (max 200 characters). Enter the payment details again:")
        bot.register_next_step_handler(msg, admin_pm_add_details, name); return
    msg = bot.send_message(
        message.chat.id,
        "➕ *ADD PAYMENT METHOD* (3/3)\n\nEnter the *instructions* shown to users (how to pay, send-money vs cash-out, minimum, rate, etc.).\nSend `-` for no instructions, or /cancel to abort.",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_pm_add_finish, name, details)

def admin_pm_add_finish(message, name, details):
    if message.from_user.id != ADMIN_ID: return
    ins = _pm_admin_text(message)
    if ins is None:
        bot.send_message(message.chat.id, "❎ Cancelled."); return
    if len(ins) > 800:
        msg = bot.send_message(message.chat.id, "❌ Too long (max 800 characters). Enter the instructions again:")
        bot.register_next_step_handler(msg, admin_pm_add_finish, name, details); return
    mid = "pm" + secrets.token_hex(3)
    while mid in get_payment_methods():
        mid = "pm" + secrets.token_hex(3)
    payment_methods[mid] = {
        "name": name, "address": details,
        "instructions": "" if ins == "-" else ins,
        "enabled": True, "builtin": False, "created_at": get_current_time(),
        "fee_enabled": False, "fee_mode": "percent", "fee_value": 0.0
    }
    save_data()
    text, markup = _pm_detail_view(mid)
    bot.send_message(message.chat.id, "✅ *Payment method added and turned ON.*\n\n" + text,
                     parse_mode="Markdown", reply_markup=markup)

# --- edit fields ---
PM_EDIT_FIELDS = {
    "name": ("name", "new *method name*", 40),
    "addr": ("address", "new *payment details* (account number / address)", 200),
    "ins":  ("instructions", "new *instructions* (send `-` to clear)", 800),
}

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_e_"))
def admin_pm_edit_start(call):
    if call.from_user.id != ADMIN_ID: return
    try:
        field_key, mid = call.data[len("adm_pm_e_"):].split("_", 1)
    except ValueError:
        bot.answer_callback_query(call.id); return
    m = get_payment_methods().get(mid)
    if field_key not in PM_EDIT_FIELDS or not m or m.get("builtin"):
        bot.answer_callback_query(call.id, "Cannot edit this method.", show_alert=True); return
    bot.answer_callback_query(call.id)
    _, label, _ = PM_EDIT_FIELDS[field_key]
    msg = bot.send_message(call.message.chat.id, f"✏️ Enter the {label}.\nSend /cancel to abort.", parse_mode="Markdown")
    bot.register_next_step_handler(msg, admin_pm_edit_apply, field_key, mid)

def admin_pm_edit_apply(message, field_key, mid):
    if message.from_user.id != ADMIN_ID: return
    value = _pm_admin_text(message)
    if value is None:
        bot.send_message(message.chat.id, "❎ Cancelled."); return
    field, label, limit = PM_EDIT_FIELDS[field_key]
    if len(value) > limit:
        msg = bot.send_message(message.chat.id, f"❌ Too long (max {limit} characters). Try again:")
        bot.register_next_step_handler(msg, admin_pm_edit_apply, field_key, mid); return
    m = get_payment_methods().get(mid)
    if not m:
        bot.send_message(message.chat.id, "❌ Method not found."); return
    if field == "instructions" and value == "-":
        value = ""
    m[field] = value
    save_data()
    text, markup = _pm_detail_view(mid)
    bot.send_message(message.chat.id, "✅ *Updated.*\n\n" + text, parse_mode="Markdown", reply_markup=markup)

# --- delete ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_d_"))
def admin_pm_delete_confirm(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_d_"):]
    m = get_payment_methods().get(mid)
    if not m or m.get("builtin"):
        bot.answer_callback_query(call.id, "This method cannot be deleted (you can turn it OFF).", show_alert=True); return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🗑 Yes, delete", callback_data=f"adm_pm_dc_{mid}"),
        types.InlineKeyboardButton("⬅️ No", callback_data=f"adm_pm_v_{mid}")
    )
    _pm_show(call, f"⚠️ Delete payment method *{pm_escape(m['name'])}*? This cannot be undone.\n(Tip: use Turn OFF to hide it temporarily.)", markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_pm_dc_"))
def admin_pm_delete_do(call):
    if call.from_user.id != ADMIN_ID: return
    mid = call.data[len("adm_pm_dc_"):]
    m = get_payment_methods().get(mid)
    if not m or m.get("builtin"):
        bot.answer_callback_query(call.id, "Method not found.", show_alert=True); return
    del payment_methods[mid]
    save_data()
    bot.answer_callback_query(call.id, "Deleted.")
    text, markup = _pm_list_view()
    _pm_show(call, text, markup)

# ================= BOT RUNNER =================
if __name__ == '__main__':
    load_data()

    # Start after loading persistent data so investments that matured
    # while the bot was offline are settled immediately after startup.
    threading.Thread(target=investment_maturity_checker, daemon=True).start()

    print(f"[{COMPANY_NAME}] Bot initialized successfully with all upgraded features...")
    bot.infinity_polling()
