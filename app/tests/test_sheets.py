# tests/test_sheets.py
import pytest
from app.services import sheets
from flask import Flask
import gspread

@pytest.mark.skip(reason="Google Sheets integration test requires live API credentials and a real spreadsheet.")
def test_get_sheet():
    app = Flask(__name__)
    app.config["GOOGLE_CREDENTIALS_FILE"] = "credentials.json"
    app.config["GOOGLE_SHEET_NAME"] = "WhatsApp Orders"
    with app.app_context():
        sheet = sheets.get_sheet()
        assert isinstance(sheet, gspread.models.Worksheet)
