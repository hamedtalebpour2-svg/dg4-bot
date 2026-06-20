import asyncio
import logging
import aiosqlite
import aiohttp

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================
TOKEN = "8208102735:AAHYRjL9sMS4qJobbbprv4cPzLCCNgatUL8"
ADMIN_ID = 8208102735
WALLET = "EVr1Xn8mm23AHh9voQea1fxGecc34pffNDFKrnkBA9Gu"

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_data = {}
delivery_state = {}

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
            price REAL,
            status TEXT,
            delivery_file TEXT
        )
        """)
        await db.commit()

# ================= START =================
@dp.message(Command("start"))
async def start(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Design Services", callback_data="services")],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="track")]
    ])

    await msg.answer("🎨 Welcome to DG4 Fiverr Mode Bot", reply_markup=kb)

# ================= SERVICES =================
@dp.callback_query(F.data == "services")
async def services(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Logo Design - $20", callback_data="logo")],
        [InlineKeyboardButton(text="Brand Identity - $45", callback_data="brand")],
        [InlineKeyboardButton(text="Social Kit - $15", callback_data="social")]
    ])

    await call.message.answer("Choose service:", reply_markup=kb)
    await call.answer()

# ================= SERVICE SELECT =================
@dp.callback_query(F.data.in_(["logo","brand","social"]))
async def select_service(call: types.CallbackQuery):
    data_map = {
        "logo": ("Logo Design", 20),
        "brand": ("Brand Identity", 45),
        "social": ("Social Kit", 15)
    }

    service, price = data_map[call.data]
    user_data[call.from_user.id] = {"service": service, "price": price}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Minimal", callback_data="minimal")],
        [InlineKeyboardButton(text="Modern", callback_data="modern")],
        [InlineKeyboardButton(text="Luxury", callback_data="luxury")],
        [InlineKeyboardButton(text="Gaming", callback_data="gaming")]
    ])

    await call.message.answer("Choose style:", reply_markup=kb)
    await call.answer()

# ================= STYLE + ORDER CREATE =================
@dp.callback_query(F.data.in_(["minimal","modern","luxury","gaming"]))
async def style(call: types.CallbackQuery):
    user_data[call.from_user.id]["style"] = call.data
    data = user_data[call.from_user.id]

    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
        INSERT INTO orders (user_id, username, service, style, price, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            call.from_user.id,
            call.from_user.username,
            data["service"],
            data["style"],
            data["price"],
            "WAITING_PAYMENT"
        ))
        await db.commit()

        async with db.execute("SELECT last_insert_rowid()") as c:
            order_id = (await c.fetchone())[0]

    await call.message.answer(
        f"""
💰 PAYMENT REQUIRED

Order ID: {order_id}
Service: {data['service']}
Style: {data['style']}
Price: ${data['price']}

Send USDT (SPL - Solana ONLY):

Wallet:
{WALLET}

After payment wait for confirmation.
"""
    )

    await bot.send_message(
        ADMIN_ID,
        f"🆕 NEW ORDER\nID: {order_id}\nUser: @{call.from_user.username}\nService: {data['service']}\nStyle: {data['style']}"
    )

    await call.answer()

# ================= SOLANA CHECK =================
async def check_solana():
    url = "https://api.mainnet-beta.solana.com"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [WALLET, {"limit": 10}]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as r:
            return await r.json()

# ================= PAYMENT LOOP =================
async def payment_loop():
    while True:
        async with aiosqlite.connect("orders.db") as db:
            async with db.execute("SELECT id, user_id, username FROM orders WHERE status='WAITING_PAYMENT'") as c:
                orders = await c.fetchall()

                data = await check_solana()

                if data.get("result"):
                    for o in orders:
                        await db.execute("UPDATE orders SET status='PAID' WHERE id=?", (o[0],))
                        await db.commit()

                        await bot.send_message(o[1], "✅ Payment confirmed! Now waiting for design.")

                        await bot.send_message(
                            ADMIN_ID,
                            f"💰 PAID ORDER\nID: {o[0]}\nUser: @{o[2]}"
                        )

        await asyncio.sleep(20)

# ================= TRACK =================
@dp.message(Command("track"))
async def track(msg: types.Message):
    async with aiosqlite.connect("orders.db") as db:
        async with db.execute("""
        SELECT status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1
        """, (msg.from_user.id,)) as c:
            r = await c.fetchone()

    if r:
        await msg.answer(f"📦 Status: {r[0]}")
    else:
        await msg.answer("No orders found.")

# ================= DELIVERY SYSTEM =================

@dp.message(Command("deliver"))
async def deliver(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    order_id = msg.get_args()
    delivery_state["order_id"] = order_id

    await msg.answer("📤 Send design file for this order (image / pdf / zip)")

@dp.message(F.document | F.photo)
async def handle_delivery(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    order_id = delivery_state.get("order_id")
    if not order_id:
        return

    file_id = None

    if msg.document:
        file_id = msg.document.file_id
    elif msg.photo:
        file_id = msg.photo[-1].file_id

    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
        UPDATE orders SET delivery_file=? WHERE id=?
        """, (file_id, order_id))
        await db.commit()

        async with db.execute("SELECT user_id FROM orders WHERE id=?", (order_id,)) as c:
            user = await c.fetchone()

    if user:
        await bot.send_document(
            user[0],
            file_id,
            caption="🎉 Your order is ready! Delivered by DG4 Studio"
        )

    await msg.answer("✅ Delivered successfully!")

# ================= MAIN =================
async def main():
    await init_db()
    asyncio.create_task(payment_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())