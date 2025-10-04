import os
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.environ.get("NOTION_API_TOKEN")  # Notion integration token (starts with ntn_ or secret_)
DS_ID  = os.environ.get("NOTION_DB_ID")     # IMPORTANT: this must be your DATA SOURCE ID
ACCOUNT_PAGE_ID = os.environ.get("ACCOUNT_PAGE_ID")

# ── 4) Helpers to turn property objects into readable text ───────────────────
# Each Notion property comes back with a 'type' and a value for that type.
# These functions just pull out plain text so printing is easy.

def text_of_title(prop: dict) -> str:
    # Title is an array of rich-text parts. We join their plain_text.
    arr = prop.get("title", []) # returns the value of the key in the dictionary or its equal to an empty list
    return "".join(piece.get("plain_text", "") for piece in arr) if arr else ""

def text_of_rich(prop: dict) -> str:
    arr = prop.get("rich_text", [])
    return "".join(piece.get("plain_text", "") for piece in arr) if arr else ""

def text_of_select(prop: dict) -> str:
    sel = prop.get("select")
    return sel.get("name") if sel else ""

def text_of_multi(prop: dict) -> str:
    return ", ".join(tag.get("name","") for tag in prop.get("multi_select", []))

def text_of_date(prop: dict) -> str:
    d = prop.get("date")
    return d.get("start") if d else ""

def text_of_number(prop: dict) -> str:
    n = prop.get("number")
    return "" if n is None else str(n)

def text_of_checkbox(prop: dict) -> str:
    v = prop.get("checkbox")
    return "true" if v else "false"

def text_of_formula(prop: dict) -> str:
    f = prop.get("formula", {})
    t = f.get("type")
    if t == "string":  return f.get("string","")
    if t == "number":  return "" if f.get("number") is None else str(f.get("number"))
    if t == "boolean": return "true" if f.get("boolean") else "false"
    if t == "date":    return (f.get("date") or {}).get("start","")
    return ""

def coerce_prop_value(prop_obj: dict) -> str:
    """
    Given a property object, return a readable string based on its type.
    Extend this if you use url, email, phone_number, people, files, relation, rollup, etc.
    """
    t = prop_obj.get("type")
    if t == "title":        return text_of_title(prop_obj)
    if t == "rich_text":    return text_of_rich(prop_obj)
    if t == "select":       return text_of_select(prop_obj)
    if t == "multi_select": return text_of_multi(prop_obj)
    if t == "date":         return text_of_date(prop_obj)
    if t == "number":       return text_of_number(prop_obj)
    if t == "checkbox":     return text_of_checkbox(prop_obj)
    if t == "formula":      return text_of_formula(prop_obj)
    return ""  # default: unknown/unsupported type

class NotionManager:
    def __init__(self):
        if not DS_ID:
            raise ValueError("Missing NOTION_DB_ID / DS_ID")
        if not NOTION_TOKEN:
            raise ValueError("Missing NOTION_API_TOKEN")

        # property display names used in your Transactions DB
        self.prop_expense_type = "Expense Type"  # relation -> Expense Types DB
        self.prop_title = "Expense Record"  # title
        self.prop_date = "Date"  # date
        self.prop_amount = "Amount"  # number

        self.ds_id = DS_ID
        self.session = None
        self.headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json",
        }
        self.expense_type_ids = {
            "Food": os.environ.get("FOOD_CAT_ID"), # copy the string before the '?' in the notion link, and you
            # must go to the page and connect it to the bot under 'connections' (or just connect the database housing all the pages to the finance bot api)
            "Shopping": os.environ.get("SHOPPING_CAT_ID"),
            "Transport": os.environ.get("TRANSPORT_CAT_ID"),
            "Work & Learning": os.environ.get("WORK_LEARNING_CAT_ID"),
            "Subscription": os.environ.get("SUBSCRIPTION_CAT_ID"),
            "Buffer": os.environ.get("BUFFER_CAT_ID"),
            "Investment": os.environ.get("INVT_CAT_ID"),
        }
        self.filter = {
        "and": [
            {"property": self.prop_date, "date": {"is_not_empty": True}},
            {"property": self.prop_expense_type, "relation": {"is_empty": True}},
        ]
        }
        self.sort_query = [{"property": "Date", "direction": "descending"}]  # latest first aka descending
        self.page_size = 50

    # ── 2) Helper: fetch the data source SCHEMA (column names & types) ───────────
    def get_data_source_schema(self) -> dict:
        """
        Returns the data source object (includes 'properties' dict).
        This lets you see the exact property names ('Amount', 'Date', etc.)
        and types ('number', 'date', 'title', 'select', ...).
        """
        self.session = requests.Session()  # create a requests session so you don't have to start a new connection each time, can reuse the same headers & is also faster
        url = f"https://api.notion.com/v1/data_sources/{self.ds_id}"
        r = self.session.get(url, headers=self.headers, timeout=30)
        r.raise_for_status()  # crash with a clear error if Notion says no
        return r.json()  # Python dict parsed from JSON response

    # ── 3) Helper: run a query to fetch rows/pages ───────────────────────────────
    def query_rows(self, page_size=50, start_cursor=None, filter_=None, sorts=None) -> dict:
        """
        Calls POST /v1/data_sources/{id}/query
        - page_size: how many rows to ask for in this request (Notion paginates)
        - start_cursor: "bookmark" to continue from the previous page of results
        - filter_: optional filter dict (e.g. { "property": "Category", "select": {"is_empty": True} })
        - sorts: optional sort rules (e.g. [{"property":"Date","direction":"descending"}])
        Returns the JSON dict with keys: results, has_more, next_cursor, etc.
        """
        self.session = requests.Session()

        body = {"page_size": page_size}
        if start_cursor:
            body["start_cursor"] = start_cursor  # tells Notion where to resume
        if filter_:
            body["filter"] = filter_
        if sorts:
            body["sorts"] = sorts

        url = f"https://api.notion.com/v1/data_sources/{self.ds_id}/query"
        r = self.session.post(url, headers=self.headers, json=body, timeout=30)  # NOTE: POST, not PATCH
        r.raise_for_status()
        return r.json()

        # ── 5) Print rows: pulls pages, loops with pagination, prints one line per row ─
    def read_rows(self, limit=20):
        """
        Prints up to 'limit' rows.
        """

        seen = 0
        empty_page_records = []
        index_of_empty_records = {}
        cursor = None

        for _ in range(self.page_size):  # we cannot have while True loops in python anywhere, so this is the next best alternative, since we are only getting 20 entries, there's no way it will go up to 50 which is our pre-defined limit
            # Ask for the next chunk of rows (page); Notion will give next_cursor if there are more
            page_size = min(self.page_size, limit - seen)  # don’t fetch more than we need -> we will never exceed the PAGE_SIZE limit which is 50
            data = self.query_rows(page_size=page_size, start_cursor=cursor, filter_=self.filter,
                              sorts=self.sort_query)
            if not data["results"]:
                # there's no empty records
                return empty_page_records, index_of_empty_records

            for page in data["results"]:
                # print("empty page found")
                # print(page)
                formatted_page_dict = self.normalize_page(page)
                empty_page_records.append(formatted_page_dict)
                index_of_empty_records[formatted_page_dict["page_id"]] = formatted_page_dict

                seen += 1
                if seen >= limit:
                    print('limit reached')
                    return  empty_page_records, index_of_empty_records # stop once we hit the requested limit
                elif seen >= len(data["results"]):
                    # we don't have any more empty rows
                    print('all records have been read')
                    return empty_page_records, index_of_empty_records

            # Handle pagination: if there are more rows, continue from next_cursor
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

    def normalize_page(self, page: dict) -> dict:
        """Return a compact record for one row (page)."""
        props = page.get("properties", {}) # this is just page['properties] but if the key don't exist it returns an empty dict

        # title: find whichever property is of type 'title'
        title = ""
        for p in props.values():
            if p.get("type") == "title":
                title =  coerce_prop_value(p)
                break

        # date/amount: prefer your configured property names, fallback if missing
        date_val = ""
        if self.prop_date in props and props[self.prop_date].get("type") == "date":
            date_val = text_of_date(props[self.prop_date])
        else:
            for p in props.values():
                if p.get("type") == "date":
                    date_val = coerce_prop_value(p)
                    break

        amount_val = ""
        if self.prop_amount in props and props[self.prop_amount].get("type") == "number":
            amount_val = text_of_number(props[self.prop_amount])
        else:
            for p in props.values():
                if p.get("type") == "number":
                    amount_val = coerce_prop_value(p)
                    break

        return {
            "page_id": page["id"],
            "title": title or "(untitled)",
            "date": date_val or "—",
            "amount": amount_val or "—",
            "url": page.get("url", ""),
            "has_expense_type": False,  # by definition for this query
        }

    def set_expense_type(self, txn_page_id: str, expense_type_page_id: str):
        """
        Update ONE row (page) to point its Expense Type relation at `expense_type_page_id`.
        Replaces whatever is there with exactly this one relation.
        """
        self.session = requests.Session()

        url = f"https://api.notion.com/v1/pages/{txn_page_id}"
        body = {
            "properties": {
                self.prop_expense_type: {
                    "relation": [{"id": expense_type_page_id}]
                }
            }
        }
        r = self.session.patch(url, headers=self.headers, json=body, timeout=30)
        r.raise_for_status()
        return True
        # return r.json()  # return updated page (or ignore and just return True)