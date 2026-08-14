from __future__ import annotations
import asyncio, os, threading
from flask import Flask, jsonify, request
import httpx
import bot

app = Flask(__name__)
WEBHOOK_SECRET = (os.getenv("TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
RENDER_EXTERNAL_URL = (os.getenv("RENDER_EXTERNAL_URL", "") or "").strip().rstrip("/")

bot.init_db()

def run_update_background(update):
    def worker():
        try:
            asyncio.run(bot.process_update(update))
        except Exception as e:
            print("Background update error:", repr(e), flush=True)
    threading.Thread(target=worker, daemon=True).start()

@app.get("/")
def index():
    return jsonify({"service":"Personal AI Maturity Bot","status":"ok","version":"0.1.0","mode":"webhook"})

@app.get("/health")
def health():
    return "OK", 200

@app.post("/telegram/webhook")
def webhook():
    if WEBHOOK_SECRET:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if supplied != WEBHOOK_SECRET:
            return "forbidden", 403
    update = request.get_json(silent=True) or {}
    run_update_background(update)
    return "ok", 200

def register_webhook():
    if not RENDER_EXTERNAL_URL:
        return
    payload = {"url": f"{RENDER_EXTERNAL_URL}/telegram/webhook", "allowed_updates": ["message","callback_query"], "drop_pending_updates": False}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{bot.API}/setWebhook", json=payload)
            r.raise_for_status()
            print("Telegram webhook:", r.json(), flush=True)
    except Exception as e:
        print("Webhook registration warning:", repr(e), flush=True)

register_webhook()
try:
    asyncio.run(bot.configure_telegram_ui())
except Exception as e:
    print("Telegram UI startup warning:", repr(e), flush=True)
