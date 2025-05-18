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
import logging
from typing import Dict, Any, List
from datetime import datetime

import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from flask import current_app

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Authorisation & worksheet access
# -------------------------------------------------

def _authorize():
    """
    Authorizes with Google Sheets API using service account credentials.
    Can use either a file or environment variable for credentials.
    """
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_file = current_app.config["GOOGLE_CREDENTIALS_FILE"]
        
        # First try to load from environment variable if it looks like JSON
        if creds_file.startswith('{') and creds_file.endswith('}'):
            try:
                import json
                creds_dict = json.loads(creds_file)
                logger.info("🔑 Using credentials from environment variable")
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                logger.info("✅ Successfully loaded credentials from environment")
            except Exception as e:
                logger.error(f"❌ Failed to parse credentials from environment: {str(e)}")
                raise
        else:
            # Fall back to file-based credentials
            if not os.path.exists(creds_file):
                error_msg = f"❌ Credentials file not found: {creds_file}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
                
            logger.info(f"🔑 Using credentials file: {creds_file}")
            
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
                logger.info("✅ Successfully loaded credentials")
            except Exception as e:
                logger.error(f"❌ Failed to load credentials: {str(e)}")
                raise
            
        # Authorize with gspread
        try:
            client = gspread.authorize(creds)
            logger.info("✅ Successfully authorized with Google Sheets")
            return client
        except Exception as e:
            logger.error(f"❌ Failed to authorize with Google Sheets: {str(e)}")
            raise
            
    except Exception as e:
        logger.error(f"❌ Authorization failed: {str(e)}")
        raise


def get_worksheet(sheet_title: str, tab_name: str):
    """
    Returns a gspread Worksheet, opening by *name* (not index).
    """
    try:
        client = _authorize()
        logger.info(f"📊 Opening sheet: {sheet_title}, tab: {tab_name}")
        
        try:
            spreadsheet = client.open(sheet_title)
            logger.info(f"✅ Successfully opened sheet: {sheet_title}")
        except Exception as e:
            logger.error(f"❌ Failed to open sheet '{sheet_title}'. Make sure it exists and is shared with the service account.")
            raise
            
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            logger.info(f"✅ Successfully opened tab: {tab_name}")
            return worksheet
        except Exception as e:
            logger.error(f"❌ Failed to open tab '{tab_name}'. Make sure it exists in the sheet.")
            raise
            
    except Exception as e:
        logger.error(f"❌ Failed to get worksheet: {str(e)}")
        raise


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
    logger.info(f"📊 Loading catalogue from sheet: {sheet_title}, tab: {tab_name}")
    
    ws = get_worksheet(sheet_title, tab_name)
    df = pd.DataFrame(ws.get_all_records())
    logger.info(f"✅ Loaded {len(df)} catalogue records")

    if "SKU_ID" not in df.columns:
        error_msg = "Catalogue sheet must have a SKU_ID column"
        logger.error(f"❌ {error_msg}")
        raise ValueError(error_msg)

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
        logger.info(f"📝 Writing {len(updated_rows)} new SKU_IDs back to sheet")
        for sheet_row in updated_rows:
            ws.update_cell(sheet_row, 1, df.at[sheet_row - 2, "SKU_ID"])
        # tiny pause so Google API doesn't rate-limit
        time.sleep(1)

    return df


# -------------------------------------------------
# Order-logging helpers
# -------------------------------------------------

def append_order(row_dict: Dict[str, Any]):
    """
    Appends a new order row into Orders_Status tab.
    The order of values should match the sheet's header.
    """
    try:
        sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
        tab_name    = current_app.config["ORDERS_TAB"]
        logger.info(f"📝 Attempting to append order to sheet: {sheet_title}, tab: {tab_name}")
        logger.info(f"📦 Order data: {row_dict}")
        
        ws = get_worksheet(sheet_title, tab_name)
        
        # Verify headers exist and match expected format
        header = ws.row_values(1)
        logger.info(f"📋 Sheet headers: {header}")
        
        # Check if we have all required columns
        required_columns = {"Timestamp", "Phone", "Query", "SKU_ID", "Qty", "Status"}
        missing_columns = required_columns - set(header)
        if missing_columns:
            error_msg = f"Missing required columns in Orders sheet: {missing_columns}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        
        row = [row_dict.get(col, "") for col in header]
        logger.info(f"🔄 Prepared row: {row}")
        
        ws.append_row(row, value_input_option="USER_ENTERED")
        logger.info("✅ Order successfully appended!")
    except Exception as e:
        logger.error(f"❌ Failed to append order: {str(e)}")
        raise


def update_status(customer_phone: str, sku_id: str, new_status: str):
    """
    Finds the first row that matches customer_phone & sku_id, updates Status col.
    """
    try:
        sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
        tab_name    = current_app.config["ORDERS_TAB"]
        logger.info(f"🔄 Updating status for phone: {customer_phone}, SKU: {sku_id} to {new_status}")
        
        ws = get_worksheet(sheet_title, tab_name)

        phone_col   = 2  # adjust if your header differs
        sku_col     = 4  # SKU_ID column in Orders sheet
        status_col  = 6  # Status column

        # Quick scan (could cache later)
        data = ws.get_all_values()
        for r, row in enumerate(data[1:], start=2):   # skip header
            if row[phone_col - 1] == customer_phone and row[sku_col - 1] == sku_id:
                ws.update_cell(r, status_col, new_status)
                logger.info("✅ Status successfully updated!")
                return
        logger.warning("⚠️ No matching order found to update status")
    except Exception as e:
        logger.error(f"❌ Failed to update status: {str(e)}")
        raise


def log_message(phone: str, message: str):
    """
    Logs a raw message to Orders_Log tab with timestamp and phone number.
    Creates the tab if it doesn't exist.
    """
    try:
        sheet_title = current_app.config["GOOGLE_SHEET_TITLE"]
        tab_name = current_app.config["ORDERS_LOG_TAB"]
        logger.info(f"[LOG] Logging raw message to sheet: {sheet_title}, tab: {tab_name}")
        
        # Get spreadsheet
        client = _authorize()
        spreadsheet = client.open(sheet_title)
        
        # Try to get worksheet, create if doesn't exist
        try:
            ws = spreadsheet.worksheet(tab_name)
            logger.info(f"[OK] Found existing tab: {tab_name}")
        except Exception:
            logger.info(f"[LOG] Creating new tab: {tab_name}")
            ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=3)
            # Add headers
            ws.append_row(["Timestamp", "Phone", "Message"], value_input_option="USER_ENTERED")
            logger.info("[OK] Created new tab with headers")
        
        # Prepare row data
        row = [
            datetime.now().isoformat(),  # Timestamp
            phone,                       # Phone
            message                      # Message
        ]
        
        ws.append_row(row, value_input_option="USER_ENTERED")
        logger.info("[OK] Message logged successfully!")
    except Exception as e:
        logger.error(f"[ERROR] Failed to log message: {str(e)}")
        # Don't raise the error - logging failure shouldn't break the main flow
