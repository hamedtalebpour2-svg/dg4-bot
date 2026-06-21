import asyncio
import logging
import aiosqlite

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "YOUR_TOKEN"
ADMIN_ID = 123456789

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= STATE =================
user_data = {}      # انتخاب سرویس + استایل
order_state = {}    # فقط برای delivery و payment

# ================= DB =================
async def init_db():
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            service TEXT,
            style TEXT,
            price INTEGER,
            status TEXT,
            file_id TEXT
        )
        """)
        await db.commit()

# ================= START =================
@dp.message(Command("start"))
async def start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Services", callback_data="services")],
        [InlineKeyboardButton(text="My Orders", callback_data="track")]
    ])
    await msg.answer("Welcome", reply_markup=kb)

# ================= SERVICES =================
@dp.callback_query(F.data == "services")
async def services(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Logo $20", callback_data="logo")],
        [InlineKeyboardButton(text="Brand $45", callback_data="brand")],
    ])
    await call.message.answer("Choose service:", reply_markup=kb)
    await call.answer()

# ================= SELECT SERVICE =================
@dp.callback_query(F.data.in_(["logo", "brand"]))
async def select_service(call: types.CallbackQuery):

    data = {
        "logo": ("Logo Design", 20),
        "brand": ("Brand Identity", 45)
    }

    service, price = data[call.data]

    user_data[call.from_user.id] = {
        "service": service,
        "price": price
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Minimal", callback_data="minimal")],
        [InlineKeyboardButton(text="Modern", callback_data="modern")],
    ])

    await call.message.answer("Choose style:", reply_markup=kb)
    await call.answer()

# ================= STYLE -> CREATE ORDER =================
@dp.callback_query(F.data.in_(["minimal", "modern"]))
async def style(call: types.CallbackQuery):

    user_id = call.from_user.id
    data = user_data.get(user_id)

    if not data:
        await call.message.answer("Session expired. /start")
        return

    style = call.data

    async with aiosqlite.connect("orders.db") as db:
        cur = await db.execute("""
        INSERT INTO orders (user_id, username, service, style, price, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            call.from_user.username,
            data["service"],
            style,
            data["price"],
            "WAITING_PAYMENT"
        ))

        await db.commit()
        order_id = cur.lastrowid

    # مهم: اینجا فقط order_state رو ست می‌کنیم
    order_state[user_id] = {
        "order_id": order_id,
        "stage": "WAITING_PAYMENT"
    }

    await call.message.answer(f"""
💰 Order Created

ID: {order_id}
Service: {data['service']}
Style: {style}
Price: ${data['price']}
""")

    await call.message.answer("Send payment screenshot now.")

    await call.answer()

# ================= PAYMENT PROOF =================
@dp.message(F.photo | F.document)
async def payment(msg: types.Message):

    state = order_state.get(msg.from_user.id)

    if not state or state.get("stage") != "WAITING_PAYMENT":
        return   # ❌ این مهمه → جلوی سفارش جدید گرفتن رو می‌گیره

    order_id = state["order_id"]

    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id

async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
        UPDATE orders SET file_id=?, status='WAITING_APPROVAL'
        WHERE id=?
        """, (file_id, order_id))
        await db.commit()

    order_state[msg.from_user.id]
["stage"] = "WAITING_APPROVAL"

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=f"Order {order_id}\nReply: /approve {order_id}"
    )

    await msg.answer("Sent to admin.")

# ================= DELIVERY =================
@dp.message(Command("deliver"))
async def deliver(msg: types.Message):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        order_id = int(msg.text.split()[1])
    except:
        await msg.answer("Use /deliver <id>")
        return

    order_state["delivery"] = {
        "order_id": order_id,
        "stage": "WAITING_FILE"
    }

    await msg.answer("Send final file now.")

# ================= FINAL FILE (FIXED BUG) =================
@dp.message(F.document | F.photo)
async def handle_delivery(msg: types.Message):

    if msg.from_user.id != ADMIN_ID:
        return

    state = order_state.get("delivery")

    if not state or state.get("stage") != "WAITING_FILE":
        return   # ❌ جلوگیری از دوباره سفارش/تداخل

    order_id = state["order_id"]

    file_id = msg.document.file_id if msg.document else msg.photo[-1].file_id

    async with aiosqlite.connect("orders.db") as db:
        cur = await db.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
        user = await cur.fetchone()

    if user:
        await bot.send_document(user[0], file_id, caption="Your order delivered")

    order_state["delivery"]["stage"] = "DONE"

    await msg.answer("Delivered!")

# ================= MAIN =================
async def main():
    await init_db()
    await dp.start_polling(bot)

if name == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
