# INDIGO BUILDERS LIMITED – Telegram Investment Bot

Telegram বট (Python)। এই ভার্সনে ইমেইল/OTP পুরোপুরি বাদ দেওয়া হয়েছে।

## যা আছে
- **শুধু পাসওয়ার্ড** দিয়ে রেজিস্ট্রেশন ও লগইন (পাসওয়ার্ড hash করে সংরক্ষিত হয়)
- **Forgot Password** চাপলে ইউজার Customer Service-এ যায়; অ্যাডমিন নতুন পাসওয়ার্ড সেট করে দেয়
- **অ্যাডমিন প্যানেল → 🔑 Change User Password**: যেকোনো ইউজারের পাসওয়ার্ড বদলানো
- ড্যাশবোর্ডে **🏆 TOTAL PROFIT (LIFETIME)** – সারা জীবনের মোট প্রফিট
- ডিপোজিট / উইথড্র / ইনভেস্টমেন্ট / কার্ড / রেফারেল আগের মতোই

## ফাইল
| ফাইল | কাজ |
|---|---|
| `main.py` | মূল বট কোড |
| `requirements.txt` | দরকারি প্যাকেজ |
| `.env` / `.env.example` | কনফিগারেশন (টোকেন, অ্যাডমিন ID ইত্যাদি) |
| `start.sh` (`run.sh`) | **সবকিছু অটোমেটিক**: Python খোঁজা, venv, প্যাকেজ ইনস্টল, ক্র্যাশ হলে রিস্টার্ট |
| `install_service.sh` | VPS-এ বুটের সময় অটো-স্টার্ট (systemd) |
| `run.bat` | Windows |
| `Procfile`, `runtime.txt` | Heroku / Railway / Render / Koyeb অটো-ডিটেক্ট |
| `Dockerfile`, `docker-compose.yml` | Docker সার্ভার |

## দ্রুত শুরু (সবচেয়ে সহজ)
```bash
unzip indigo_bot.zip && cd indigo_bot
nano .env            # BOT_TOKEN ও ADMIN_ID বসান
bash start.sh        # বাকি সব অটোমেটিক
```
> প্রথমবার `.env` না থাকলে স্ক্রিপ্ট নিজেই বানিয়ে দেয়। টোকেন না বসালে পরিষ্কার এরর দেখায়।

## কোন সার্ভারে কী করবেন
| সার্ভার | কমান্ড |
|---|---|
| **VPS / Linux / WSL / Termux** | `bash start.sh` |
| **VPS-এ ২৪/৭ (রিবুটের পরেও)** | `sudo bash install_service.sh` |
| **Docker** | `docker compose up -d --build` |
| **Heroku / Railway / Render / Koyeb** | ফোল্ডার আপলোড করুন — `Procfile` দেখে নিজে `python main.py` চালাবে। Dashboard-এর Environment Variables-এ `BOT_TOKEN`, `ADMIN_ID` ইত্যাদি দিন। Worker টাইপ সার্ভিস বানান (Web নয়)। |
| **Windows** | `run.bat` ডাবল ক্লিক |
| **হাতে হাতে** | `pip install -r requirements.txt && python3 main.py` |

> ফ্রি হোস্টে (Heroku/Render ইত্যাদি) ফাইল সিস্টেম রিসেট হয়, তাই ইউজার ডাটা (`bot_database.json`) হারাতে পারে। স্থায়ী ডাটার জন্য VPS বা Docker (volume সহ) ব্যবহার করুন।

## 💱 পেমেন্ট মেথড ম্যানেজমেন্ট (নতুন)
অ্যাডমিন প্যানেল → **💱 Payment Methods (Add / ON-OFF)**
- **➕ Add Payment Method:** নাম (যেমন Mobile Wallet) → অ্যাকাউন্ট নম্বর/ওয়ালেট অ্যাড্রেস → ইনস্ট্রাকশন, এই ৩ ধাপে নতুন মেথড যোগ হয়।
- **✅ / ⛔ ON-OFF:** মেথডে ট্যাপ করে *Turn ON / Turn OFF* — OFF মেথড ইউজার দেখতে পায় না।
- **✏️ Edit / 🗑 Delete:** নাম, ডিটেইলস, ইনস্ট্রাকশন বদলানো বা মেথড মুছে ফেলা।
- বিল্ট-ইন **USDT (TRC20)** মেথড আগের মতোই অটো ব্লকচেইন যাচাই করে; শুধু ON/OFF করা যায় (ঠিকানা `.env`-এর `USDT_ADDRESS` থেকে)।
- অ্যাডমিনের যোগ করা মেথডে ইউজার পেমেন্টের পর Transaction ID + স্ক্রিনশট দেয়, অ্যাডমিন Approve/Reject করে (ম্যানুয়াল রিভিউ)।
- একটি মেথড চালু থাকলে ইউজার সরাসরি সেটির পেজে যায়; একাধিক চালু থাকলে বেছে নেওয়ার মেনু আসে; সব বন্ধ থাকলে "Deposits temporarily unavailable" দেখায়।
- মেথডের তালিকা `bot_database.json`-এ সেভ হয়।

### উত্তোলন (Withdraw) ও ফি
- **ইউজারের অ্যাকাউন্ট সেভ:** ⚙️ Account Settings → 💳 Wallet / Address Settings-এ প্রতিটি ON মেথডের জন্য "Set / Update Account Number" বাটন আসে। ইউজার নিজের নম্বর/অ্যাড্রেস সেভ করে।
- **উইথড্র:** পরিমাণ বাছার পর একাধিক মেথড চালু থাকলে **পেমেন্ট মেথড বাটন** আসে; একটি চালু থাকলে সরাসরি সেটিতে যায়। এরপর আগের মতোই কনফার্ম → Card PIN → অ্যাডমিন Approve/Reject (Reject করলে টাকা ফেরত)।
- **ফি অন/অফ:** অ্যাডমিন প্যানেল → **💸 Withdrawal Fee (ON / OFF)** (সব মেথড একসাথে) অথবা Payment Methods → মেথড → **💸 Withdrawal Fee**।
  - অ্যাডমিনের যোগ করা মেথডে **💸 Set Fee Amount** দিয়ে ফি ঠিক করা যায়: `2%` (পরিমাণের শতাংশ) অথবা `1.5` (নির্দিষ্ট ডলার)। নতুন মেথডে ফি ডিফল্ট OFF।
  - বিল্ট-ইন USDT-এ ফি ডিফল্ট ON (আগের মতো 1.5 TRX); OFF করলে কোনো ফি কাটে না।
- **ইউজারের অ্যাকাউন্ট নম্বর:** ইউজার ⚙️ Account Settings → 💳 Wallet / Address Settings-এ প্রতিটি চালু মেথডের জন্য "Set Account Number" বাটন পায় এবং নিজের নম্বর সেভ/আপডেট করতে পারে। মেথড OFF করলে বাটন লুকিয়ে যায় (সেভ করা নম্বর থেকে যায়)।

## .env ব্যাখ্যা
| ভ্যারিয়েবল | মানে |
|---|---|
| `BOT_TOKEN` | BotFather-এর টোকেন (আবশ্যক) |
| `BOT_USERNAME` | বটের ইউজারনেম, `@` ছাড়া |
| `ADMIN_ID` | অ্যাডমিনের Telegram numeric ID |
| `CHANNEL_ID` | বাধ্যতামূলক জয়েন চ্যানেল (বট ওই চ্যানেলের অ্যাডমিন হতে হবে) |
| `USDT_ADDRESS` | ডিপোজিট গ্রহণের TRC20 ওয়ালেট |
| `SUPPORT_URL` | কাস্টমার সার্ভিসের টেলিগ্রাম লিংক |
| `DB_FILE` | ডাটাবেস JSON ফাইল (ডিফল্ট `bot_database.json`) |

## Termux (Android)
```bash
pkg update && pkg install python -y
bash start.sh
```
ব্যাকগ্রাউন্ডে: `pkg install tmux` → `tmux` → `bash start.sh`।

## অ্যাডমিন ব্যবহার
- বটে `👑 Admin Panel` খুলুন → **🔑 Change User Password** → ইউজার খুঁজুন (username বা ID) → নতুন পাসওয়ার্ড লিখুন।
  পাসওয়ার্ডের মেসেজ চ্যাট থেকে নিজে থেকে মুছে যায়। নতুন পাসওয়ার্ডটি ইউজারকে সাপোর্ট চ্যাটে জানিয়ে দিন।

## নিরাপত্তা টিপস
- `.env` ও `bot_database.json` কখনো কাউকে শেয়ার বা GitHub-এ আপলোড করবেন না।
- `BOT_TOKEN` ফাঁস হলে BotFather থেকে `/revoke` করুন।

## সমস্যা হলে
- `ModuleNotFoundError` → `pip install -r requirements.txt` আবার চালান।
- বট সাড়া দেয় না → `BOT_TOKEN` ঠিক আছে কিনা এবং একই টোকেনে অন্য কোথাও বট চলছে কিনা দেখুন।
- চ্যানেল ভেরিফিকেশন ব্যর্থ → বটকে `CHANNEL_ID` চ্যানেলের অ্যাডমিন বানান।
