"""
Google Sheets helper layer
———————————
• Authorises via service-account JSON.
• Grabs worksheets by title & tab name.
• Loads the Catalogue tab into a DataFrame and back-fills missing SKU_IDs
  (unique 8-char hex).
• Appends / updates rows in the Orders tabs.
"""

import os
import uuid
import time
from typing import Dict, Any, List

import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from flask import current_app


# -------------------------------------------------
# Authorisation & worksheet access
# -------------------------------------------------

def _authorize():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_file = current_app.config["GOOGLE_CREDENTIALS_FILE"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    return gspread.authorize(creds)


def get_worksheet(sheet_title: str, tab_name: str):
    """
    Returns a gspread Worksheet, opening by *name* (not index).
    """
    client = _authorize()
    spreadsheet = client.open(sheet_title)
    return spreadsheet.worksheet(tab_name)


# -------------------------------------------------
# Catalogue helpers
# -------------------------------------------------

def _generate_unique_id(existing_ids: set[str]) -> str:
    """
    Generates an 8-char hex string that does not collide with existing_ids.
    """
    while True:
        new_id = uuid.uuid4().hex[:8]
        if new_id not in existing_ids:
            return new_id


def load_catalogue_df() -> pd.DataFrame:
    """
    Reads the Catalogue tab into a DataFrame.
    If any row has a blank SKU_ID, assigns a unique ID and writes it back.
    Returns the DataFrame (with fresh IDs).
    """
    sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
    tab_name    = current_app.config["CATALOGUE_TAB"]
    ws = get_worksheet(sheet_title, tab_name)

    df = pd.DataFrame(ws.get_all_records())

    if "SKU_ID" not in df.columns:
        raise ValueError("Catalogue sheet must have a SKU_ID column")

    # Back-fill missing IDs
    ids_seen = set(df["SKU_ID"].dropna().astype(str))
    updated_rows: List[int] = []

    for idx, row in df.iterrows():
        if not row["SKU_ID"]:
            new_id = _generate_unique_id(ids_seen)
            ids_seen.add(new_id)
            df.at[idx, "SKU_ID"] = new_id
            updated_rows.append(idx + 2)   # +2 -> sheet row number (header + 1)

    # Write back any new IDs
    if updated_rows:
        for sheet_row in updated_rows:
            ws.update_cell(sheet_row, 1, df.at[sheet_row - 2, "SKU_ID"])
        # tiny pause so Google API doesn’t rate-limit
        time.sleep(1)

    return df


# -------------------------------------------------
# Order-logging helpers
# -------------------------------------------------

def append_order(row_dict: Dict[str, Any]):
    """
    Appends a new order row into Orders_Status tab.
    The order of values should match the sheet’s header.
    """
    sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
    tab_name    = current_app.config["ORDERS_TAB"]
    ws = get_worksheet(sheet_title, tab_name)

    header = ws.row_values(1)
    row = [row_dict.get(col, "") for col in header]
    ws.append_row(row, value_input_option="USER_ENTERED")


def update_status(customer_phone: str, sku_id: str, new_status: str):
    """
    Finds the first row that matches customer_phone & sku_id, updates Status col.
    """
    sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
    tab_name    = current_app.config["ORDERS_TAB"]
    ws = get_worksheet(sheet_title, tab_name)

    phone_col   = 2  # adjust if your header differs
    sku_col     = 4  # SKU_ID column in Orders sheet
    status_col  = 6  # Status column

    # Quick scan (could cache later)
    data = ws.get_all_values()
    for r, row in enumerate(data[1:], start=2):   # skip header
        if row[phone_col - 1] == customer_phone and row[sku_col - 1] == sku_id:
            ws.update_cell(r, status_col, new_status)
            return
