# main.py
import os, requests
from flask import Flask, request
from telebot import types
from dotenv import load_dotenv
from telegram_manager import BotManager   # your class defined ONLY in telegram_manager.py

load_dotenv()

WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g. https://3a44d98a8670.ngrok-free.app/webhook
assert WEBHOOK_URL and WEBHOOK_URL.startswith("https://") and WEBHOOK_URL.endswith("/webhook")

bot = BotManager().bot
app = Flask(__name__)

# set webhook
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

@app.route("/", methods=["GET"])
def home():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    if not request.is_json:
        return "invalid", 403
    update = types.Update.de_json(request.get_json())  # dict → Update
    bot.process_new_updates([update])
    print(update)
    return "", 200

if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    print("getWebhookInfo:", requests.get(
        f"https://api.telegram.org/bot{token}/getWebhookInfo"
    ).json())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
