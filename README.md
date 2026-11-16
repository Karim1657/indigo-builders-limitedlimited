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

## 💱 পেমেন্ট মেথড ম্যানেজমেন্ট
সব ডিপোজিট ও উত্তোলন অ্যাডমিন-পরিচালিত পেমেন্ট মেথডের মাধ্যমে চলে। আগের USDT (TRC20) অটো-যাচাই মেথড সম্পূর্ণ সরানো হয়েছে।

**রেডিমেড ৮টি মেথড** (প্রথমবার চালুর সময় নিজে থেকে তৈরি হয়, ইনস্ট্রাকশনসহ): Binance, Bybit, Bitget, KuCoin, Litecoin (LTC), TRX (TRC20), Solana (SOL), Dogecoin (DOGE)।
- অ্যাডমিন প্যানেল → **💱 Payment Methods** → মেথড → **Edit Details** দিয়ে ডিপোজিটের অ্যাড্রেস/ID বসান। **ডিপোজিট ডিটেইলস না বসানো পর্যন্ত মেথডটি ডিপোজিটে দেখায় না** (উত্তোলনে দেখায়)।
- **Edit Instructions** দিয়ে ইনস্ট্রাকশন বদলানো যায়; **Reset Instructions to Default** দিয়ে আগেরটা ফেরানো যায়।
- ✅/⛔ **Turn ON / OFF**: OFF মেথড ইউজার ডিপোজিট, উত্তোলন ও সেটিংস কোথাও দেখে না। রেডিমেড মেথডও মুছে ফেলা যায় (মুছলে আর ফিরে আসে না)।

**নতুন মেথড যোগ:** ➕ Add Payment Method → নাম → ডিপোজিট ডিটেইলস → ইনস্ট্রাকশন (৩ ধাপ)। অ্যাডমিন সর্বোচ্চ **৫০টি** নতুন মেথড যোগ করতে পারে (রেডিমেড ৮টি এর বাইরে)।

**ডিপোজিট:** পরিমাণ বাছার পর মেথড বাটন → ডিটেইলস ও ইনস্ট্রাকশন → ইউজার Transaction ID ও স্ক্রিনশট দেয় → অ্যাডমিন Approve/Reject।

**উত্তোলন:** ইউজার ⚙️ Account Settings → 💳 Wallet / Address Settings-এ প্রতিটি মেথডের জন্য নিজের অ্যাকাউন্ট নম্বর/অ্যাড্রেস সেভ করে। উত্তোলনে পরিমাণ বাছার পর মেথড বাটন আসে → কনফার্ম → Card PIN → অ্যাডমিন Approve/Reject (Reject করলে টাকা ফেরত)।

**উত্তোলন ফি অন/অফ:** অ্যাডমিন প্যানেল → **💸 Withdrawal Fee (ON / OFF)**
- **মাস্টার সুইচ:** এক ট্যাপে সব মেথডের উত্তোলন ফি চালু/বন্ধ। বন্ধ থাকলে কোনো ফি কাটে না।
- **মেথডভিত্তিক ফি:** প্রতিটি মেথডে আলাদা ON/OFF। ফির পরিমাণ মেথডের পেজে **💸 Set Fee Amount** থেকে ঠিক করুন: `2%` (পরিমাণের শতাংশ) অথবা `1.5` (নির্দিষ্ট ডলার)। ডিফল্টে সব মেথডের ফি OFF।

সব মেথড ও সেটিংস `bot_database.json`-এ সেভ হয়।

## .env ব্যাখ্যা
| ভ্যারিয়েবল | মানে |
|---|---|
| `BOT_TOKEN` | BotFather-এর টোকেন (আবশ্যক) |
| `BOT_USERNAME` | বটের ইউজারনেম, `@` ছাড়া |
| `ADMIN_ID` | অ্যাডমিনের Telegram numeric ID |
| `CHANNEL_ID` | বাধ্যতামূলক জয়েন চ্যানেল (বট ওই চ্যানেলের অ্যাডমিন হতে হবে) |
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
