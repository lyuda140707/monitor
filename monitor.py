import os
import asyncio
import time
from aiohttp import web, ClientSession

BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
PING_URL = os.getenv("PING_URL", "https://relax-time2.onrender.com/ping")

async def send_telegram(text: str):
    if not BOT_TOKEN or not ADMIN_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": ADMIN_ID, "text": text}
    async with ClientSession() as session:
        await session.post(url, data=data)

async def check_once():
    try:
        async with ClientSession() as session:
            start = time.perf_counter()
            async with session.get(PING_URL, timeout=10) as resp:
                latency = int((time.perf_counter() - start) * 1000)
                if resp.status == 200:
                    return f"✅ WebApp працює (200)\n⏱ {latency} ms"
                else:
                    return f"⚠️ Відповідь {resp.status}"
    except Exception as e:
        return f"❌ Помилка: {e}"

async def scheduler():
    while True:
        msg = await check_once()
        await send_telegram(msg)
        await asyncio.sleep(60)  # чекати 1 годину

# HTTP-сервер для Render
async def handle(request):
    return web.Response(text="Monitor running")

async def main():
    asyncio.create_task(scheduler())
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 5000)))
    await site.start()
    await asyncio.Event().wait()  # щоб не зупинявся

if __name__ == "__main__":
    asyncio.run(main())
