from __future__ import annotations

import os
from flask import Flask, request, jsonify
from bot import configure_telegram_webhook, process_update

app = Flask(__name__)

@app.get("/")
def health():
    return jsonify({"ok": True, "service": "Personal AI Maturity Bot", "version": "1.0"})

@app.post("/telegram/webhook")
def telegram_webhook():
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if received != secret:
            return jsonify({"ok": False, "error": "unauthorized"}), 403
    update = request.get_json(silent=True) or {}
    process_update(update)
    return jsonify({"ok": True})

with app.app_context():
    configure_telegram_webhook()
