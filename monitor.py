import os
import asyncio
import time
from aiohttp import web, ClientSession

BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
PING_URL = os.getenv("PING_URL", "https://relax-time2.onrender.com/ping")

PING_EVERY_SECONDS = int(os.getenv("PING_EVERY_SECONDS", "3600"))

last_status = {"ok": None, "code": None, "ts": None, "latency_ms": None, "error": None}


def fmt_status():
    if last_status["ok"] is None:
        return "ℹ️ Ще немає даних, очікуйте першу перевірку."
    when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(last_status["ts"]))
    if last_status["ok"]:
        return f"✅ WebApp працює ({last_status['code']})\n⏱ {last_status['latency_ms']} ms\n🕒 {when}"
    else:
        if last_status["code"] is not None:
            return f"⚠️ Відповідь {last_status['code']}\n🕒 {when}"
        return f"❌ Помилка: {last_status['error']}\n🕒 {when}"


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
                ok = (resp.status == 200)
                last_status.update(
                    {"ok": ok, "code": resp.status, "ts": time.time(), "latency_ms": latency, "error": None}
                )
                if ok:
                    return f"✅ WebApp працює ({resp.status})\n⏱ {latency} ms"
                else:
                    return f"⚠️ Відповідь {resp.status}"
    except Exception as e:
        last_status.update({"ok": False, "code": None, "ts": time.time(), "latency_ms": None, "error": repr(e)})
        return f"❌ Помилка: {e}"


async def scheduler():
    while True:
        msg = await check_once()
        await send_telegram(msg)
        await asyncio.sleep(PING_EVERY_SECONDS)


# ------------------- Web-сервер для Render -------------------
async def handle_root(request):
    return web.Response(text="Monitor running\n\n" + fmt_status())


async def handle_health(request):
    return web.json_response({"status": last_status, "ping_url": PING_URL, "every_s": PING_EVERY_SECONDS})


# ✅ Тепер /status робить новий пінг при кожному виклику
async def handle_status(request):
    msg = await check_once()   # запускаємо перевірку прямо зараз
    return web.Response(text=msg)



async def main():
    asyncio.create_task(scheduler())
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/status", handle_status)  # нова ручка
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 5000)))
    await site.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
