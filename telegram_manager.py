# telegram_manager.py
import os, html, secrets
from dotenv import load_dotenv, find_dotenv
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from notion_manager import NotionManager

load_dotenv(find_dotenv(), override=True)

TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing BOT_TOKEN / TELEGRAM_BOT_TOKEN")

notion_bot = NotionManager()

class BotManager:
    def __init__(self):
        # ⭐(Q1) parse_mode="HTML" lets us use <b>, <i>, <a href=...> etc. for nicer messages.
        self.bot = TeleBot(token=TOKEN, parse_mode="HTML")

        # ⭐(Q6) keep track of message ids we sent per chat so we can delete/clean on next /search
        self.user_messages: dict[int, list[int]] = {}

        # ⭐(Q2) callback map: short key → (txn_page_id, expense_type_page_id)
        # Reason: Telegram callback_data must be ≤ 64 bytes; two Notion IDs won't fit.
        self.callback_map: dict[str, tuple[str, str]] = {}

        # ── Handlers ──
        self.bot.message_handler(commands=['start'])(self.start)
        self.bot.message_handler(commands=['search'])(self.categorise_transactions)

        # ⭐(Q3) Run handle_set_type only for callback_data beginning with "SET:"
        self.bot.callback_query_handler(func=lambda callback: callback.data and callback.data.startswith("SET:"))(self.handle_set_type)

    # ── Button helpers ──
    def _store_cb(self, txn_page_id: str, expense_type_page_id: str) -> str:
        # ⭐(Q4) Create a short random “claim ticket” (URL-safe), store full ids server-side.
        key = secrets.token_urlsafe(6)  # e.g., 'dQ4kQ0T8'
        self.callback_map[key] = (txn_page_id, expense_type_page_id) # it is a tuple
        return key

    def _keyboard_for(self, transaction_page_id: str) -> InlineKeyboardMarkup:
        # ⭐(Q5) Build a keyboard with one button per category.
        # The button carries only a short key (SET:<key>), not the long Notion IDs.
        keyboard = InlineKeyboardMarkup(row_width=2)
        buttons = []
        for name, exp_id in notion_bot.expense_type_ids.items():
            if not exp_id:  # skip categories missing env ids
                continue
            callback_key = self._store_cb(transaction_page_id, exp_id)
            buttons.append(InlineKeyboardButton(text=name, callback_data=f"SET:{callback_key}"))

        if not buttons:
            # if we have no categories set in our notion database, then no buttons will be appending cos there's the dictionary
            # notion_bot.expense_type_ids is empty... so we set it to disabled (then later in the callback, in 'handle_settype function' if we check that it is disabled, we don't do anything)
            buttons.append(InlineKeyboardButton(text="No categories configured", callback_data="SET:disabled"))

        keyboard.add(*buttons)

        # add delete button (instead of adding it together with the buttons, we add it as a separate entity so that the delete button appears on the next row, as a standalone button)
        del_key = self._store_cb(transaction_page_id, "DELETE")
        keyboard.add(InlineKeyboardButton(text="🗑 Delete", callback_data=f"SET:{del_key}"))
        return keyboard

    def _format_record(self, rec: dict) -> str:
        # Pretty one-record message body
        parts = [f"<b>{html.escape(rec.get('title','(untitled)'))}</b>"]
        if rec.get("date"):   parts.append(f"Date: {html.escape(rec['date'])}")
        if rec.get("amount"): parts.append(f"Amount: {html.escape(str(rec['amount']))}")
        if rec.get("url"):    parts.append(f'<a href="{rec["url"]}">Open in Notion</a>')
        return "\n".join(parts)

    # ── Command handlers ──
    def start(self, message):
        self.bot.send_message(
            chat_id=message.chat.id,
            text="📈 Welcome! Send /search to assign categories to uncategorised transactions."
        )

    def categorise_transactions(self, message):
        chat_id = message.chat.id

        # ⭐(Q6) Clean previous batch we sent (if any)
        for message_id in self.user_messages.get(chat_id, []):
            try:
                self.bot.delete_message(chat_id, message_id)
            except Exception as e:
                print("delete_message failed:", e)
        self.user_messages[chat_id] = []

        # ⭐(Q6.1) Show loading while we query Notion
        loading = self.bot.send_message(chat_id, "🔎 Gathering transactions, please wait…") # 🔴 if no transactions it seems to time out, fix this error.
        self.user_messages[chat_id].append(loading.message_id) # add this loading message to the user_messages

        # ⭐(Q6.2) Use the NotionManager method that RETURNS data.
        # If you hadn't added it, you'd get AttributeError (meaning the method doesn't exist).
        try:
            # print('🔴 checkpoint reached')
            records, _index = notion_bot.read_rows(limit=50)
            print(records)
            print(_index)
        except ValueError:
            print('error here')
            self.bot.edit_message_text("✅ Nothing to categorise. ValueError encountered", chat_id, loading.message_id)
        else:
            if not records:
                self.bot.edit_message_text("✅ Nothing to categorise.", chat_id, loading.message_id)
                return

            # turn the loading into a header
            try:
                self.bot.edit_message_text(f"Found {len(records)} uncategorised record(s):", chat_id, loading.message_id)
            except Exception as e:
                # print(f"Exception encountered: {e}")
                pass

            # Send each record with inline buttons
            for rec in records:
                text = self._format_record(rec)
                kb   = self._keyboard_for(rec["page_id"])
                sent = self.bot.send_message(chat_id, text, reply_markup=kb)
                self.user_messages[chat_id].append(sent.message_id) # add this message to the user_messages so we can clean it up if needed

    # ── Callback handler (button tap) ──
    def handle_set_type(self, c: types.CallbackQuery):
        # c is a CallbackQuery (⭐ explained): c.data is our short key; c.message is the original Message with the keyboard
        print(f"handle_set_type reached with data={getattr(c, 'data', None)}")
        if not (c.data and c.data.startswith("SET:")):
            self.bot.answer_callback_query(c.id, "Ignoring.", show_alert=False)
            return

        key = c.data.split(":", 1)[1] # maxsplit means we only split it once, it is like to play safe.
        if key == "disabled":
            self.bot.answer_callback_query(c.id, "No categories configured.", show_alert=True)
            return

        # Resolve short key → full ids
        try:
            transaction_id, exp_type_id = self.callback_map.pop(key) # .pop looks up the key -> removes the key -> returns the value that is stored at the key, in this case it is a tuple, see _store_cb
            # however if we get a key error when trying to remove this key from the dict, means the key no longer exists in the dictionary
            # hence we just do nothing, but must accept the button press by the user by writing answer_callback_query otherwise the button will keep loading ('spinning' - in telegram phrasing)
            # it IS OPTIONAL to get the data returned by .pop, but we need this data for later (see below, in order to update notion)
        except KeyError:
            # Common KeyError reasons:
            # - The user tapped the same button twice (we already removed it). OR The bot restarted (our in-memory map was cleared).
            # IMPORTANT: Always acknowledge the tap so Telegram stops the loading spinner. can choose to send a message afterwards to update user. the text sent over is optional and not visible to users.

            self.bot.answer_callback_query(c.id, "Invalid/expired button.", show_alert=False)
            # call answer_callback_query on every button press, usually with show_alert=False, and then do your real UI updates by editing/deleting/sending messages.

            return

        # 🔴 Delete branch
        if exp_type_id == "DELETE":
            print("Deleted block reached.")
            try:
                notion_bot.delete_expense(transaction_id)
                self.bot.answer_callback_query(c.id, "Deleted. ⛔️", show_alert=False)
                try:
                    # remove keyboard, then annotate
                    self.bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
                except Exception as e:
                    print(f"🔴 error encountered when editing message {e}")
                try:
                    self.bot.edit_message_text(c.message.text + "\n\n☑️ Deleted.", c.message.chat.id,
                                               c.message.message_id)
                except Exception:
                    self.bot.send_message(c.message.chat.id, "☑️ Deleted.")
            except Exception as e:
                self.bot.answer_callback_query(c.id, "Delete failed ❌", show_alert=False)
                err = self.bot.send_message(c.message.chat.id, f"❌ Failed: <code>{html.escape(str(e))}</code>")
                self.user_messages[c.message.chat.id].append(err.message_id) # basically adding the error message id to the list of messages sent so that we can delete it later
            return

        # Update Notion
        try:
            print("Updating notion block reached.")
            notion_bot.set_expense_type(transaction_id, exp_type_id)
            self.bot.answer_callback_query(c.id, "Updated ✅", show_alert=False)

            # ⭐(Q7) First remove the keyboard (so users can’t double-tap), then annotate success.
            # (You could instead delete the message and send a short “Categorised” line.)
            try:
                self.bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
            except Exception:
                pass
            try:
                self.bot.edit_message_text(c.message.text + "\n\n✅ Categorised.", c.message.chat.id, c.message.message_id)
            except Exception:
                # fallback: just confirm
                self.bot.send_message(c.message.chat.id, "✅ Categorised.")
        except Exception as e:
            print(c.message.chat.id)
            self.bot.answer_callback_query(c.id, "Update failed ❌", show_alert=False)
            error_message = self.bot.send_message(c.message.chat.id, f"❌ Failed: <code>{html.escape(str(e))}</code>") # the notion page could have been deleted, that's why error.
            self.user_messages[c.message.chat.id].append(error_message.message_id)  # clean up the error messages if needed
