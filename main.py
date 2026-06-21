import asyncio
import logging
import aiosqlite

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIG =================
TOKEN = "8208102735:AAFn76BbTnXXYaBR7Cv07GLb-jtL-Yq8YEc"
ADMIN_ID = 7833539117

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= STATE =================
user_state = {}        # ساخت سفارش
delivery_state = {}    # ارسال فایل نهایی

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
            file_id TEXT
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
    await msg.answer("🎨 Welcome to DG4 Bot", reply_markup=kb)

# ================= SERVICES =================
@dp.callback_query(F.data == "services")
async def services(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Logo - $20", callback_data="logo")],
        [InlineKeyboardButton(text="Brand - $45", callback_data="brand")],
        [InlineKeyboardButton(text="Social - $15", callback_data="social")]
    ])

    await call.message.answer("Choose service:")
    await call.message.answer("Services:", reply_markup=kb)
    await call.answer()

# ================= SELECT SERVICE =================
@dp.callback_query(F.data.in_(["logo", "brand", "social"]))
async def select_service(call: types.CallbackQuery):

    data = {
        "logo": ("Logo Design", 20),
        "brand": ("Brand Identity", 45),
        "social": ("Social Kit", 15)
    }

    service, price = data[call.data]

    user_state[call.from_user.id] = {
        "service": service,
        "price": price
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Minimal", callback_data="minimal")],
        [InlineKeyboardButton(text="Modern", callback_data="modern")],
        [InlineKeyboardButton(text="Luxury", callback_data="luxury")],
        [InlineKeyboardButton(text="Gaming", callback_data="gaming")]
    ])

    await call.message.answer("Choose style:", reply_markup=kb)
    await call.answer()

# ================= STYLE =================
@dp.callback_query(F.data.in_(["minimal", "modern", "luxury", "gaming"]))
async def style(call: types.CallbackQuery):

    user_id = call.from_user.id
    data = user_state.get(user_id)

    if not data:
        await call.message.answer("❌ Session expired. Send /start again.")
        return

    data["style"] = call.data

    async with aiosqlite.connect("orders.db") as db:
        cur = await db.execute("""
            INSERT INTO orders (user_id, username, service, style, price, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            call.from_user.username,
            data["service"],
            data["style"],
            data["price"],
            "WAITING_PAYMENT"
        ))

        await db.commit()
        order_id = cur.lastrowid

    await call.message.answer(
        f"""
💰 PAYMENT REQUIRED

Order ID: {order_id}
Service: {data['service']}
Style: {data['style']}
Price: ${data['price']}

────────────────────
💳 PAYMENT INFO

Token: USDT (SPL)
Network: Solana ONLY ⚡️

Wallet:
EVr1Xn8mm23AHh9voQea1fxGecc34pffNDFKrnkBA9Gu

────────────────────

⚠️ Send ONLY USDT on Solana network

📸 After payment send screenshot here.
"""
    )

    await bot.send_message(
        ADMIN_ID,
        f"""
🆕 NEW ORDER

ID: {order_id}
User: @{call.from_user.username}
Service: {data['service']}
Style: {data['style']}
Price: ${data['price']}
"""
    )

    await call.answer()

# ================= PAYMENT PROOF =================
@dp.message(F.photo | F.document)
async def payment(msg: types.Message):

    order_id = delivery_state.get(msg.from_user.id)

    if not order_id:
        return

    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
            UPDATE orders SET file_id=?, status='WAITING_APPROVAL'
            WHERE id=?
        """, (file_id, order_id))
        await db.commit()

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=f"💳 Payment proof\nOrder ID: {order_id}\nReply /approve {order_id}"
    )

    await msg.answer("✅ Sent to admin for review.")

# ================= APPROVE =================
@dp.message(Command("approve"))
async def approve(msg: types.Message):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        order_id = int(msg.text.split()[1])
    except:
        await msg.answer("Use: /approve <order_id>")
        return

    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
            UPDATE orders SET status='PAID' WHERE id=?
        """, (order_id,))
        await db.commit()

        cur = await db.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
        user = await cur.fetchone()

    if user:
        await bot.send_message(user[0], "✅ Payment confirmed!")

    await msg.answer("Approved.")

# ================= DELIVER =================
@dp.message(Command("deliver"))
async def deliver(msg: types.Message):

    if msg.from_user.id != ADMIN_ID:
        return

    try:
        order_id = int(msg.text.split()[1])
    except:
        await msg.answer("Use: /deliver <order_id>")
        return

    delivery_state["order"] = order_id
    await msg.answer("📤 Send final file now.")

# ================= FINAL FILE =================
@dp.message(F.photo | F.document)
async def final_file(msg: types.Message):

    if msg.from_user.id != ADMIN_ID:
        return

    order_id = delivery_state.get("order")
    if not order_id:
        return

    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect("orders.db") as db:
        cur = await db.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
        user = await cur.fetchone()

        if user:
            await bot.send_document(
                user[0],
                file_id,
                caption="🎉 Your order is delivered!"
            )

            await db.execute(
                "UPDATE orders SET status='DELIVERED' WHERE id=?",
                (order_id,)
            )
            await db.commit()

    delivery_state.pop("order", None)

    await msg.answer("✅ Delivered successfully")

# ================= TRACK =================
@dp.message(Command("track"))
async def track(msg: types.Message):

    async with aiosqlite.connect("orders.db") as db:
        cur = await db.execute("""
            SELECT status FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1
        """, (msg.from_user.id,))
        r = await cur.fetchone()

    if r:
        await msg.answer(f"📦 Status: {r[0]}")
    else:
        await msg.answer("No orders found.")

# ================= MAIN =================
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
