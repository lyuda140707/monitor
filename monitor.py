import os
import asyncio
import time
from aiohttp import web, ClientSession

BOT_TOKEN = os.getenv("MONITOR_BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
PING_URL = os.getenv("PING_URL", "https://relax-time2.onrender.com/ping")

PING_EVERY_SECONDS = int(os.getenv("PING_EVERY_SECONDS", "3600"))

last_status = {"ok": None, "code": None, "ts": None, "latency_ms": None, "error": None}
offset = 0  # для polling


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


async def send_telegram(text: str, chat_id=None):
    if not BOT_TOKEN:
        return
    if chat_id is None:
        chat_id = ADMIN_ID
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
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
                return ok
    except Exception as e:
        last_status.update(
            {"ok": False, "code": None, "ts": time.time(), "latency_ms": None, "error": repr(e)}
        )
        return False


async def scheduler():
    prev_ok = None
    while True:
        ok = await check_once()
        # 🔔 Надсилаємо повідомлення тільки якщо стан змінився
        if ok != prev_ok:
            msg = fmt_status()
            await send_telegram(msg)
            prev_ok = ok
        await asyncio.sleep(PING_EVERY_SECONDS)



# ------------------- Polling для команд -------------------
async def polling():
    global offset
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    while True:
        try:
            async with ClientSession() as session:
                params = {"timeout": 30, "offset": offset + 1}
                async with session.get(api_url, params=params, timeout=35) as resp:
                    data = await resp.json()
                    if "result" in data:
                        for update in data["result"]:
                            offset = update["update_id"]
                            if "message" in update:
                                chat_id = update["message"]["chat"]["id"]
                                text = update["message"].get("text", "")
                                if text == "/status":
                                    msg = await check_once()
                                    await send_telegram(msg, chat_id=chat_id)
        except Exception:
            await asyncio.sleep(5)


# ------------------- Self-ping для Render -------------------
async def self_ping():
    url = os.getenv("SELF_URL", "https://relax-monitor.onrender.com/healthz")
    while True:
        try:
            async with ClientSession() as s:
                await s.get(url, timeout=10)
        except Exception as e:
            print("Self-ping error:", e)
        await asyncio.sleep(300)  # кожні 5 хв


# ------------------- Web-сервер для Render -------------------
async def handle_root(request):
    return web.Response(text="Monitor running\n\n" + fmt_status())


async def handle_health(request):
    return web.json_response({"status": last_status, "ping_url": PING_URL, "every_s": PING_EVERY_SECONDS})


async def main():
    asyncio.create_task(scheduler())
    asyncio.create_task(polling())
    asyncio.create_task(self_ping())  # 🟢 самопінг
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/healthz", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 5000)))
    await site.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
