# 🚀 GetSMSWeb Pro Telegram Bot

## ✅ Features
- 💰 Live Balance Check
- 📋 Global Services List (paginated + search)
- 🛒 Buy Global SMS Number → Auto OTP Poll
- 🔐 Get OTP (Global) — manual & auto
- ❌ Cancel Global Order & Refund
- 📱 Buy Local Number → Auto OTP Poll
- 💬 Get OTP (Local)
- 🚫 Cancel Local Number & Refund
- 📧 Mail / VPN Services List
- 🛍️ Buy Mail / VPN Accounts
- 👑 Admin Panel (/admin, /stats)
- ⚡ Fully Async (no blocking)

---

## ⚙️ Installation & Run

### Method 1 — Local / Termux

```bash
# 1. Python install karo (Termux)
pkg install python

# 2. Dependencies install karo
pip install -r requirements.txt

# 3. Bot run karo
python bot.py
```

### Method 2 — Server (VPS/Cloud)

```bash
# Clone ya upload karo bot.py aur requirements.txt
pip install -r requirements.txt
python bot.py

# Background mein run karne ke liye:
nohup python bot.py &

# Ya screen use karo:
screen -S smsbot
python bot.py
# Ctrl+A then D to detach
```

### Method 3 — systemd Service (Linux Server)

```bash
# /etc/systemd/system/smsbot.service banaao
[Unit]
Description=GetSMSWeb Telegram Bot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/bot.py
WorkingDirectory=/path/to/
Restart=always
User=root

[Install]
WantedBy=multi-user.target

# Enable & start
systemctl enable smsbot
systemctl start smsbot
systemctl status smsbot
```

---

## 📁 Files

| File | Description |
|------|-------------|
| `bot.py` | Main bot — all-in-one |
| `requirements.txt` | Python dependencies |
| `bot.log` | Auto-generated log file |

---

## 🔧 Configuration (bot.py ke andar)

```python
BOT_TOKEN   = "your_bot_token"
API_KEY     = "your_api_key"
ADMIN_ID    = 123456789       # Your Telegram ID
```

---

## 📋 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main Menu |
| `/balance` | Quick Balance Check |
| `/admin` | Admin Panel (admin only) |
| `/stats` | Bot Statistics (admin only) |

---

## ⚡ Powered by
- **aiogram 3.x** — Async Telegram Bot Framework
- **aiohttp** — Async HTTP Client
- **GetSMSWeb API** — SMS/Mail/VPN Services
