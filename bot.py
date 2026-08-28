#!/usr/bin/env python3
# ============================================================
#   🚀 GetSMSWeb ALL-IN-ONE Professional Telegram Bot
#   Author  : Professional Bot Builder
#   Version : 3.0 FINAL
#   API     : getsmsweb.com
# ============================================================

import asyncio
import logging
import sys
import json
import time
import re
from typing import Optional, Dict, Any, List

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ──────────────────────────────────────────────
#  ⚙️  CONFIGURATION
# ──────────────────────────────────────────────
BOT_TOKEN   = "8908741277:AAF5V_2Tl4k7deM2sk_M4ETy71ug6cPrJ5U"
API_KEY     = "251d10af35f6f1ddc7bf892418545fad"
ADMIN_ID    = 8068314746                          # Your Telegram Chat ID
BASE_URL    = "https://getsmsweb.com/developer_api"
OTP_POLL_INTERVAL = 10    # seconds between OTP checks
OTP_MAX_WAIT      = 300   # max 5 minutes wait for OTP

# ──────────────────────────────────────────────
#  📝  LOGGING SETUP
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("SMSBot")

# ──────────────────────────────────────────────
#  🗃️  IN-MEMORY STORE  (replace with DB for prod)
# ──────────────────────────────────────────────
active_orders: Dict[int, Dict] = {}   # user_id -> {order_id, service, ts}
active_locals: Dict[int, str]  = {}   # user_id -> phone

# ──────────────────────────────────────────────
#  🌐  ASYNC HTTP HELPER
# ──────────────────────────────────────────────
async def api_call(params: dict) -> Optional[Dict]:
    """Make an async GET request to the GetSMSWeb API."""
    params["api_key"] = API_KEY
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BASE_URL, params=params) as resp:
                text = await resp.text()
                logger.info(f"API [{params.get('action')}] → {text[:200]}")
                # Try JSON first, then plain-text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text.strip()}
    except aiohttp.ClientError as e:
        logger.error(f"HTTP Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

# ──────────────────────────────────────────────
#  🎨  EMOJI & FORMATTING HELPERS
# ──────────────────────────────────────────────
def fmt_balance(data: dict) -> str:
    if not data:
        return "❌ API se connect nahi ho saka."
    bal = data.get("balance") or data.get("raw") or data.get("data") or str(data)
    return (
        f"💰 <b>Aapka Wallet Balance</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Balance: <code>{bal}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 Real-time data from GetSMSWeb"
    )

def fmt_service_page(services: list, page: int, per_page: int = 12) -> str:
    start = page * per_page
    chunk = services[start : start + per_page]
    lines = [f"📋 <b>Global Services — Page {page+1}</b>\n━━━━━━━━━━━━━━━━━━━━"]
    for s in chunk:
        sid   = s.get("id") or s.get("service_id") or "?"
        name  = s.get("name") or s.get("service") or "Unknown"
        price = s.get("price") or s.get("cost") or "?"
        stock = s.get("stock") or s.get("qty") or "?"
        lines.append(
            f"🆔 <code>{sid}</code> │ 📱 {name}\n"
            f"   💲 Price: <b>{price}</b>  │  📦 Stock: <b>{stock}</b>"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def fmt_order(data: dict, service_id: str) -> str:
    if not data:
        return "❌ Number kharidne mein error aaya."
    oid  = data.get("order_id") or data.get("id") or data.get("raw") or str(data)
    phone= data.get("phone") or data.get("number") or "—"
    return (
        f"✅ <b>Number Successfully Purchased!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order ID  : <code>{oid}</code>\n"
        f"📞 Number    : <code>{phone}</code>\n"
        f"🛒 Service ID: <code>{service_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ OTP aane ka wait kar raha hun...\n"
        f"❌ Cancel karne ke liye neeche button dabao."
    )

def fmt_otp(data: dict) -> str:
    if not data:
        return "⏳ Abhi tak OTP nahi aaya..."
    otp  = data.get("otp") or data.get("code") or data.get("sms") or data.get("raw")
    if not otp or str(otp).lower() in ("null","none","","false","0"):
        return "⏳ OTP abhi tak nahi aaya, wait karo..."
    return (
        f"🎉 <b>OTP Received!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 OTP Code: <b><code>{otp}</code></b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Copy karke use karo!"
    )

def fmt_mail_service_page(services: list, page: int, per_page: int = 10) -> str:
    start = page * per_page
    chunk = services[start : start + per_page]
    lines = [f"📧 <b>Mail / VPN Services — Page {page+1}</b>\n━━━━━━━━━━━━━━━━━━━━"]
    for s in chunk:
        pid   = s.get("id") or s.get("product_id") or "?"
        name  = s.get("name") or s.get("product") or "Unknown"
        price = s.get("price") or "?"
        stock = s.get("stock") or s.get("qty") or "?"
        lines.append(
            f"🆔 <code>{pid}</code> │ 📧 {name}\n"
            f"   💲 Price: <b>{price}</b>  │  📦 Stock: <b>{stock}</b>"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# ──────────────────────────────────────────────
#  ⌨️  KEYBOARDS
# ──────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Balance Check",      callback_data="balance"),
        InlineKeyboardButton(text="📋 Global Services",   callback_data="services_0"),
    )
    builder.row(
        InlineKeyboardButton(text="🛒 Buy Global Number", callback_data="buy_global"),
        InlineKeyboardButton(text="🔐 Get OTP (Global)",  callback_data="get_otp"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel Global Order",callback_data="cancel_global"),
        InlineKeyboardButton(text="📱 Buy Local Number",  callback_data="buy_local"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 Get OTP (Local)",   callback_data="get_local_otp"),
        InlineKeyboardButton(text="🚫 Cancel Local",      callback_data="cancel_local"),
    )
    builder.row(
        InlineKeyboardButton(text="📧 Mail/VPN Services", callback_data="mail_services_0"),
        InlineKeyboardButton(text="🛍️ Buy Mail/VPN",      callback_data="buy_mail"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh / Home",    callback_data="home"),
        InlineKeyboardButton(text="ℹ️ Help",              callback_data="help"),
    )
    return builder.as_markup()

def cancel_order_kb(order_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Cancel & Refund", callback_data=f"do_cancel_global_{order_id}"),
        InlineKeyboardButton(text="🔁 Check OTP Again", callback_data=f"do_check_otp_{order_id}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="home"))
    return builder.as_markup()

def cancel_local_kb(phone: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Cancel Local & Refund", callback_data=f"do_cancel_local_{phone}"),
        InlineKeyboardButton(text="🔁 Check OTP Again",      callback_data=f"do_check_local_otp_{phone}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="home"))
    return builder.as_markup()

def services_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"services_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"services_{page+1}"))
    builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text="🔍 Search Service", callback_data="search_service"),
        InlineKeyboardButton(text="🛒 Buy Now",        callback_data="buy_global"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="home"))
    return builder.as_markup()

def mail_nav_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"mail_services_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"mail_services_{page+1}"))
    builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text="🛍️ Buy Mail/VPN", callback_data="buy_mail"),
        InlineKeyboardButton(text="🏠 Main Menu",    callback_data="home"),
    )
    return builder.as_markup()

def back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Main Menu", callback_data="home"))
    return builder.as_markup()

# ──────────────────────────────────────────────
#  📦  FSM STATES
# ──────────────────────────────────────────────
class BuyGlobal(StatesGroup):
    waiting_service_id = State()

class GetOTP(StatesGroup):
    waiting_order_id = State()

class CancelGlobal(StatesGroup):
    waiting_order_id = State()

class GetLocalOTP(StatesGroup):
    waiting_phone = State()

class CancelLocal(StatesGroup):
    waiting_phone = State()

class BuyMail(StatesGroup):
    waiting_product_id = State()
    waiting_quantity    = State()

class SearchService(StatesGroup):
    waiting_query = State()

# ──────────────────────────────────────────────
#  🤖  ROUTER & BOT SETUP
# ──────────────────────────────────────────────
router = Router()
bot    = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp     = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# ──────────────────────────────────────────────
#  🏠  START / HOME
# ──────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = msg.from_user
    welcome = (
        f"🎉 <b>Welcome, {user.first_name}!</b>\n\n"
        f"🤖 <b>GetSMSWeb Pro Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Global SMS Number Buy/OTP/Cancel\n"
        f"✅ Local Number Buy/OTP/Cancel\n"
        f"✅ Mail & VPN Account Purchase\n"
        f"✅ Live Balance & Stock Check\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Neeche se apna kaam choose karo:"
    )
    await msg.answer(welcome, reply_markup=main_menu_kb())

@router.callback_query(F.data == "home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    user = cb.from_user
    welcome = (
        f"🏠 <b>Main Menu — {user.first_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Kya karna chahte ho?"
    )
    await cb.message.edit_text(welcome, reply_markup=main_menu_kb())

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()

# ──────────────────────────────────────────────
#  ℹ️  HELP
# ──────────────────────────────────────────────
@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    text = (
        "ℹ️ <b>Bot Usage Guide</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🌍 Global SMS Number:</b>\n"
        "1️⃣ 'Global Services' se Service ID dekho\n"
        "2️⃣ 'Buy Global Number' → Service ID daalo\n"
        "3️⃣ OTP aane ka wait karo (auto check hota hai)\n"
        "4️⃣ Cancel karna ho to 'Cancel Global Order'\n\n"
        "<b>📱 Local Number:</b>\n"
        "1️⃣ 'Buy Local Number' → automatic number milega\n"
        "2️⃣ 'Get OTP (Local)' → phone number daalo\n"
        "3️⃣ 'Cancel Local' → 1 min baad cancel kar sakte ho\n\n"
        "<b>📧 Mail / VPN:</b>\n"
        "1️⃣ 'Mail/VPN Services' se Product ID dekho\n"
        "2️⃣ 'Buy Mail/VPN' → Product ID & quantity daalo\n\n"
        "<b>💰 Balance:</b>\n"
        "   'Balance Check' se live balance dekho\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ Powered by GetSMSWeb API"
    )
    await cb.message.edit_text(text, reply_markup=back_kb())

# ──────────────────────────────────────────────
#  💰  BALANCE
# ──────────────────────────────────────────────
@router.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    await cb.answer("⏳ Balance check ho raha hai...")
    data = await api_call({"action": "get_balance"})
    await cb.message.edit_text(fmt_balance(data), reply_markup=back_kb())

@router.message(Command("balance"))
async def cmd_balance(msg: Message):
    data = await api_call({"action": "get_balance"})
    await msg.answer(fmt_balance(data), reply_markup=back_kb())

# ──────────────────────────────────────────────
#  📋  GLOBAL SERVICES LIST (Paginated)
# ──────────────────────────────────────────────
_services_cache: List[dict] = []
_services_cache_time: float = 0

async def get_services_cached() -> List[dict]:
    global _services_cache, _services_cache_time
    if _services_cache and (time.time() - _services_cache_time) < 300:
        return _services_cache
    data = await api_call({"action": "get_services"})
    if isinstance(data, list):
        _services_cache = data
    elif isinstance(data, dict):
        _services_cache = data.get("services") or data.get("data") or []
    _services_cache_time = time.time()
    return _services_cache

@router.callback_query(F.data.startswith("services_"))
async def cb_services(cb: CallbackQuery):
    await cb.answer("⏳ Services load ho rahi hain...")
    page = int(cb.data.split("_")[1])
    services = await get_services_cached()
    if not services:
        await cb.message.edit_text(
            "❌ Services load nahi ho sakein. Dobara try karo.",
            reply_markup=back_kb()
        )
        return
    per_page   = 12
    total_pages = max(1, (len(services) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    text = fmt_service_page(services, page, per_page)
    kb   = services_nav_kb(page, total_pages)
    await cb.message.edit_text(text, reply_markup=kb)

# ──────────────────────────────────────────────
#  🔍  SEARCH SERVICE
# ──────────────────────────────────────────────
@router.callback_query(F.data == "search_service")
async def cb_search_service(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SearchService.waiting_query)
    await cb.message.edit_text(
        "🔍 <b>Service Search</b>\n\n"
        "Service ka naam ya ID type karo:",
        reply_markup=back_kb()
    )

@router.message(SearchService.waiting_query)
async def process_search(msg: Message, state: FSMContext):
    await state.clear()
    query = msg.text.strip().lower()
    services = await get_services_cached()
    results = [
        s for s in services
        if query in str(s.get("name","")).lower()
        or query in str(s.get("id","")).lower()
        or query in str(s.get("service","")).lower()
    ]
    if not results:
        await msg.answer(
            f"❌ '<b>{query}</b>' ke liye koi service nahi mili.",
            reply_markup=back_kb()
        )
        return
    text = fmt_service_page(results, 0, 15)
    await msg.answer(text, reply_markup=back_kb())

# ──────────────────────────────────────────────
#  🛒  BUY GLOBAL NUMBER
# ──────────────────────────────────────────────
@router.callback_query(F.data == "buy_global")
async def cb_buy_global(cb: CallbackQuery, state: FSMContext):
    await state.set_state(BuyGlobal.waiting_service_id)
    await cb.message.edit_text(
        "🛒 <b>Buy Global Number</b>\n\n"
        "Service ID daalo (Services list se copy karo):\n"
        "Example: <code>123</code>",
        reply_markup=back_kb()
    )

@router.message(BuyGlobal.waiting_service_id)
async def process_buy_global(msg: Message, state: FSMContext):
    service_id = msg.text.strip()
    if not service_id.isdigit():
        await msg.answer("❌ Valid Service ID daalo (sirf numbers).", reply_markup=back_kb())
        await state.clear()
        return
    await state.clear()
    wait_msg = await msg.answer("⏳ Number kharida ja raha hai...")
    data = await api_call({"action": "buy_number", "service_id": service_id})
    if not data:
        await wait_msg.edit_text("❌ Number kharidne mein error. Balance check karo.", reply_markup=back_kb())
        return
    # Extract order ID
    order_id = (
        data.get("order_id")
        or data.get("id")
        or data.get("orderId")
        or (data.get("raw") if data.get("raw") else None)
    )
    if not order_id:
        raw = json.dumps(data, ensure_ascii=False)
        await wait_msg.edit_text(
            f"⚠️ Response mila lekin order ID unclear hai:\n<code>{raw}</code>",
            reply_markup=back_kb()
        )
        return
    order_id = str(order_id)
    active_orders[msg.from_user.id] = {
        "order_id": order_id,
        "service_id": service_id,
        "ts": time.time(),
    }
    text = fmt_order(data, service_id)
    kb   = cancel_order_kb(order_id)
    sent = await wait_msg.edit_text(text, reply_markup=kb)
    # Auto-poll OTP in background
    asyncio.create_task(
        auto_poll_otp(msg.from_user.id, order_id, sent.chat.id, sent.message_id)
    )

async def auto_poll_otp(user_id: int, order_id: str, chat_id: int, message_id: int):
    """Background task: poll OTP every OTP_POLL_INTERVAL seconds."""
    elapsed = 0
    while elapsed < OTP_MAX_WAIT:
        await asyncio.sleep(OTP_POLL_INTERVAL)
        elapsed += OTP_POLL_INTERVAL
        data = await api_call({"action": "get_otp", "order_id": order_id})
        if data:
            otp = (
                data.get("otp")
                or data.get("code")
                or data.get("sms")
                or data.get("raw")
            )
            if otp and str(otp).lower() not in ("null","none","","false","0","no otp"):
                text = (
                    f"🎉 <b>OTP Received!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🆔 Order ID : <code>{order_id}</code>\n"
                    f"🔐 OTP Code : <b><code>{otp}</code></b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Copy karke use karo!"
                )
                try:
                    await bot.edit_message_text(
                        text=text,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=back_kb(),
                    )
                except Exception:
                    await bot.send_message(chat_id, text, reply_markup=back_kb())
                active_orders.pop(user_id, None)
                return
    # Timeout
    timeout_text = (
        f"⏰ <b>OTP Timeout!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Order ID: <code>{order_id}</code>\n"
        f"❌ {OTP_MAX_WAIT//60} minute mein OTP nahi aaya.\n"
        f"Cancel karke refund lo."
    )
    kb = cancel_order_kb(order_id)
    try:
        await bot.edit_message_text(
            text=timeout_text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=kb,
        )
    except Exception:
        await bot.send_message(chat_id, timeout_text, reply_markup=kb)

# ──────────────────────────────────────────────
#  🔐  GET OTP (GLOBAL) — Manual
# ──────────────────────────────────────────────
@router.callback_query(F.data == "get_otp")
async def cb_get_otp(cb: CallbackQuery, state: FSMContext):
    await state.set_state(GetOTP.waiting_order_id)
    await cb.message.edit_text(
        "🔐 <b>Get OTP (Global)</b>\n\n"
        "Order ID daalo:\nExample: <code>987654</code>",
        reply_markup=back_kb()
    )

@router.message(GetOTP.waiting_order_id)
async def process_get_otp(msg: Message, state: FSMContext):
    order_id = msg.text.strip()
    await state.clear()
    wait_msg = await msg.answer("⏳ OTP check ho raha hai...")
    data = await api_call({"action": "get_otp", "order_id": order_id})
    otp_text = fmt_otp(data) if data else "❌ OTP check fail. Order ID sahi hai?"
    await wait_msg.edit_text(otp_text, reply_markup=cancel_order_kb(order_id))

@router.callback_query(F.data.startswith("do_check_otp_"))
async def cb_do_check_otp(cb: CallbackQuery):
    order_id = cb.data.replace("do_check_otp_", "")
    await cb.answer("⏳ Checking...")
    data = await api_call({"action": "get_otp", "order_id": order_id})
    otp_text = fmt_otp(data) if data else "❌ OTP nahi aaya abhi."
    await cb.message.edit_text(otp_text, reply_markup=cancel_order_kb(order_id))

# ──────────────────────────────────────────────
#  ❌  CANCEL GLOBAL ORDER
# ──────────────────────────────────────────────
@router.callback_query(F.data == "cancel_global")
async def cb_cancel_global(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CancelGlobal.waiting_order_id)
    await cb.message.edit_text(
        "❌ <b>Cancel Global Order</b>\n\n"
        "Cancel karne wala Order ID daalo:",
        reply_markup=back_kb()
    )

@router.message(CancelGlobal.waiting_order_id)
async def process_cancel_global(msg: Message, state: FSMContext):
    order_id = msg.text.strip()
    await state.clear()
    wait_msg = await msg.answer("⏳ Cancel ho raha hai...")
    data = await api_call({"action": "cancel_order", "order_id": order_id})
    result = data.get("raw") or data.get("status") or data.get("message") or str(data) if data else "Error"
    await wait_msg.edit_text(
        f"🔄 <b>Cancel Result</b>\n\n"
        f"🆔 Order: <code>{order_id}</code>\n"
        f"📩 Response: <code>{result}</code>",
        reply_markup=back_kb()
    )

@router.callback_query(F.data.startswith("do_cancel_global_"))
async def cb_do_cancel_global(cb: CallbackQuery):
    order_id = cb.data.replace("do_cancel_global_", "")
    await cb.answer("⏳ Cancelling...")
    data = await api_call({"action": "cancel_order", "order_id": order_id})
    result = data.get("raw") or data.get("status") or data.get("message") or str(data) if data else "Error"
    active_orders.pop(cb.from_user.id, None)
    await cb.message.edit_text(
        f"✅ <b>Order Cancelled & Refund Initiated</b>\n\n"
        f"🆔 Order: <code>{order_id}</code>\n"
        f"📩 Response: <code>{result}</code>",
        reply_markup=back_kb()
    )

# ──────────────────────────────────────────────
#  📱  BUY LOCAL NUMBER
# ──────────────────────────────────────────────
@router.callback_query(F.data == "buy_local")
async def cb_buy_local(cb: CallbackQuery):
    await cb.answer("⏳ Local number kharida ja raha hai...")
    data = await api_call({"action": "buy_local"})
    if not data:
        await cb.message.edit_text("❌ Local number nahi mila. Balance check karo.", reply_markup=back_kb())
        return
    phone = (
        data.get("phone")
        or data.get("number")
        or data.get("raw")
        or str(data)
    )
    active_locals[cb.from_user.id] = str(phone)
    text = (
        f"✅ <b>Local Number Purchased!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📞 Phone: <code>{phone}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ OTP check karne ke liye neeche button dabao.\n"
        f"❌ 1 minute baad cancel kar sakte ho."
    )
    await cb.message.edit_text(text, reply_markup=cancel_local_kb(str(phone)))
    # Auto-poll local OTP
    asyncio.create_task(
        auto_poll_local_otp(
            cb.from_user.id,
            str(phone),
            cb.message.chat.id,
            cb.message.message_id,
        )
    )

async def auto_poll_local_otp(user_id: int, phone: str, chat_id: int, message_id: int):
    await asyncio.sleep(30)  # give 30s before first check
    elapsed = 30
    while elapsed < OTP_MAX_WAIT:
        await asyncio.sleep(OTP_POLL_INTERVAL)
        elapsed += OTP_POLL_INTERVAL
        data = await api_call({"action": "get_local_otp", "phone": phone})
        if data:
            otp = (
                data.get("otp")
                or data.get("code")
                or data.get("sms")
                or data.get("raw")
            )
            if otp and str(otp).lower() not in ("null","none","","false","0","no otp"):
                text = (
                    f"🎉 <b>Local OTP Received!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📞 Phone : <code>{phone}</code>\n"
                    f"🔐 OTP   : <b><code>{otp}</code></b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Copy karke use karo!"
                )
                try:
                    await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=back_kb())
                except Exception:
                    await bot.send_message(chat_id, text, reply_markup=back_kb())
                active_locals.pop(user_id, None)
                return
    timeout_text = (
        f"⏰ <b>Local OTP Timeout!</b>\n📞 Phone: <code>{phone}</code>\n"
        f"❌ OTP nahi aaya. Cancel karke refund lo."
    )
    try:
        await bot.edit_message_text(timeout_text, chat_id=chat_id, message_id=message_id, reply_markup=cancel_local_kb(phone))
    except Exception:
        await bot.send_message(chat_id, timeout_text, reply_markup=cancel_local_kb(phone))

# ──────────────────────────────────────────────
#  💬  GET OTP LOCAL — Manual
# ──────────────────────────────────────────────
@router.callback_query(F.data == "get_local_otp")
async def cb_get_local_otp(cb: CallbackQuery, state: FSMContext):
    await state.set_state(GetLocalOTP.waiting_phone)
    await cb.message.edit_text(
        "💬 <b>Get Local OTP</b>\n\n"
        "Phone number daalo (+ ke saath ya bina):\n"
        "Example: <code>+919876543210</code>",
        reply_markup=back_kb()
    )

@router.message(GetLocalOTP.waiting_phone)
async def process_get_local_otp(msg: Message, state: FSMContext):
    phone = msg.text.strip().replace(" ", "")
    await state.clear()
    wait_msg = await msg.answer("⏳ OTP check ho raha hai...")
    data = await api_call({"action": "get_local_otp", "phone": phone})
    otp_text = fmt_otp(data) if data else "❌ OTP nahi mila. Phone number sahi hai?"
    await wait_msg.edit_text(otp_text, reply_markup=cancel_local_kb(phone))

@router.callback_query(F.data.startswith("do_check_local_otp_"))
async def cb_do_check_local_otp(cb: CallbackQuery):
    phone = cb.data.replace("do_check_local_otp_", "")
    await cb.answer("⏳ Checking...")
    data = await api_call({"action": "get_local_otp", "phone": phone})
    otp_text = fmt_otp(data) if data else "⏳ OTP abhi nahi aaya."
    await cb.message.edit_text(otp_text, reply_markup=cancel_local_kb(phone))

# ──────────────────────────────────────────────
#  🚫  CANCEL LOCAL NUMBER
# ──────────────────────────────────────────────
@router.callback_query(F.data == "cancel_local")
async def cb_cancel_local(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CancelLocal.waiting_phone)
    await cb.message.edit_text(
        "🚫 <b>Cancel Local Number</b>\n\n"
        "Phone number daalo jo cancel karna hai:\n"
        "Example: <code>+919876543210</code>",
        reply_markup=back_kb()
    )

@router.message(CancelLocal.waiting_phone)
async def process_cancel_local(msg: Message, state: FSMContext):
    phone = msg.text.strip().replace(" ", "")
    await state.clear()
    wait_msg = await msg.answer("⏳ Cancel ho raha hai...")
    data = await api_call({"action": "cancel_local", "phone": phone})
    result = data.get("raw") or data.get("status") or data.get("message") or str(data) if data else "Error"
    active_locals.pop(msg.from_user.id, None)
    await wait_msg.edit_text(
        f"✅ <b>Local Number Cancel & Refund</b>\n\n"
        f"📞 Phone: <code>{phone}</code>\n"
        f"📩 Response: <code>{result}</code>",
        reply_markup=back_kb()
    )

@router.callback_query(F.data.startswith("do_cancel_local_"))
async def cb_do_cancel_local(cb: CallbackQuery):
    phone = cb.data.replace("do_cancel_local_", "")
    await cb.answer("⏳ Cancelling...")
    data = await api_call({"action": "cancel_local", "phone": phone})
    result = data.get("raw") or data.get("status") or data.get("message") or str(data) if data else "Error"
    active_locals.pop(cb.from_user.id, None)
    await cb.message.edit_text(
        f"✅ <b>Local Number Cancelled!</b>\n\n"
        f"📞 Phone: <code>{phone}</code>\n"
        f"📩 Response: <code>{result}</code>",
        reply_markup=back_kb()
    )

# ──────────────────────────────────────────────
#  📧  MAIL / VPN SERVICES
# ──────────────────────────────────────────────
_mail_cache: List[dict] = []
_mail_cache_time: float = 0

async def get_mail_cached() -> List[dict]:
    global _mail_cache, _mail_cache_time
    if _mail_cache and (time.time() - _mail_cache_time) < 300:
        return _mail_cache
    data = await api_call({"action": "get_mail_services"})
    if isinstance(data, list):
        _mail_cache = data
    elif isinstance(data, dict):
        _mail_cache = data.get("services") or data.get("data") or []
    _mail_cache_time = time.time()
    return _mail_cache

@router.callback_query(F.data.startswith("mail_services_"))
async def cb_mail_services(cb: CallbackQuery):
    await cb.answer("⏳ Mail services load ho rahi hain...")
    page = int(cb.data.split("_")[2])
    services = await get_mail_cached()
    if not services:
        await cb.message.edit_text(
            "❌ Mail/VPN services nahi mili. Dobara try karo.",
            reply_markup=back_kb()
        )
        return
    per_page    = 10
    total_pages = max(1, (len(services) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    text = fmt_mail_service_page(services, page, per_page)
    kb   = mail_nav_kb(page, total_pages)
    await cb.message.edit_text(text, reply_markup=kb)

# ──────────────────────────────────────────────
#  🛍️  BUY MAIL / VPN
# ──────────────────────────────────────────────
@router.callback_query(F.data == "buy_mail")
async def cb_buy_mail(cb: CallbackQuery, state: FSMContext):
    await state.set_state(BuyMail.waiting_product_id)
    await cb.message.edit_text(
        "🛍️ <b>Buy Mail / VPN</b>\n\n"
        "Product ID daalo (Mail/VPN Services list se):\n"
        "Example: <code>45</code>",
        reply_markup=back_kb()
    )

@router.message(BuyMail.waiting_product_id)
async def process_buy_mail_pid(msg: Message, state: FSMContext):
    pid = msg.text.strip()
    if not pid.isdigit():
        await msg.answer("❌ Valid Product ID daalo (sirf numbers).", reply_markup=back_kb())
        await state.clear()
        return
    await state.update_data(product_id=pid)
    await state.set_state(BuyMail.waiting_quantity)
    await msg.answer(
        f"📦 <b>Quantity</b>\n\nKitne accounts chahiye?\n"
        f"(1-10, default ke liye 1 type karo)"
    )

@router.message(BuyMail.waiting_quantity)
async def process_buy_mail_qty(msg: Message, state: FSMContext):
    qty_text = msg.text.strip()
    qty = 1
    if qty_text.isdigit():
        qty = max(1, min(int(qty_text), 10))
    data_state = await state.get_data()
    pid = data_state.get("product_id", "1")
    await state.clear()
    wait_msg = await msg.answer(f"⏳ {qty} Mail/VPN account kharida ja raha hai...")
    data = await api_call({"action": "buy_mail", "product_id": pid, "quantity": qty})
    if not data:
        await wait_msg.edit_text("❌ Purchase fail. Balance ya Product ID check karo.", reply_markup=back_kb())
        return
    # Format accounts
    accounts = data.get("accounts") or data.get("data") or data.get("raw") or str(data)
    if isinstance(accounts, list):
        lines = [f"📧 <b>Mail/VPN Accounts Purchased!</b>\n━━━━━━━━━━━━━━━━━━━━"]
        for i, acc in enumerate(accounts, 1):
            if isinstance(acc, dict):
                email = acc.get("email") or acc.get("username") or acc.get("login") or "?"
                pw    = acc.get("password") or acc.get("pass") or "?"
                lines.append(f"{i}. 📧 <code>{email}</code>\n   🔑 <code>{pw}</code>")
            else:
                lines.append(f"{i}. <code>{acc}</code>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        text = "\n".join(lines)
    else:
        raw = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(accounts)
        text = (
            f"✅ <b>Purchase Successful!</b>\n\n"
            f"📦 Product ID : <code>{pid}</code>\n"
            f"🔢 Quantity   : <code>{qty}</code>\n"
            f"📩 Details    :\n<code>{raw}</code>"
        )
    await wait_msg.edit_text(text, reply_markup=back_kb())

# ──────────────────────────────────────────────
#  👑  ADMIN COMMANDS
# ──────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Access Denied!")
        return
    text = (
        f"👑 <b>Admin Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Bot is Running\n"
        f"👥 Active Global Orders : {len(active_orders)}\n"
        f"📱 Active Local Numbers : {len(active_locals)}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔧 Commands:\n"
        f"/admin - Admin Panel\n"
        f"/broadcast - Send to all (not implemented)\n"
        f"/stats - Same as admin\n"
    )
    await msg.answer(text, reply_markup=back_kb())

@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("❌ Access Denied!")
        return
    data = await api_call({"action": "get_balance"})
    bal = data.get("balance") or data.get("raw") or "?" if data else "?"
    text = (
        f"📊 <b>Bot Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Balance            : <b>{bal}</b>\n"
        f"🌍 Active Orders      : <b>{len(active_orders)}</b>\n"
        f"📱 Active Local Nums  : <b>{len(active_locals)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await msg.answer(text, reply_markup=back_kb())

# ──────────────────────────────────────────────
#  🚦  UNKNOWN TEXT HANDLER
# ──────────────────────────────────────────────
@router.message()
async def unknown_msg(msg: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return  # FSM handle karega
    await msg.answer(
        "❓ Samajh nahi aaya. /start dabao ya menu use karo.",
        reply_markup=back_kb()
    )

# ──────────────────────────────────────────────
#  🚀  STARTUP
# ──────────────────────────────────────────────
async def set_commands():
    commands = [
        BotCommand(command="start",   description="🏠 Main Menu"),
        BotCommand(command="balance", description="💰 Balance Check"),
        BotCommand(command="admin",   description="👑 Admin Panel"),
        BotCommand(command="stats",   description="📊 Bot Stats"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logger.info("🚀 Bot starting...")
    await set_commands()
    # Notify admin on start
    try:
        await bot.send_message(
            ADMIN_ID,
            "🟢 <b>Bot Successfully Started!</b>\n\n"
            "✅ GetSMSWeb Pro Bot is now ONLINE.\n"
            "Use /start to begin.",
        )
    except Exception as e:
        logger.warning(f"Admin notify failed: {e}")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
