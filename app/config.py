# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment

class Config:
    DEBUG                 = os.getenv('DEBUG', 'False') == 'True'
    PORT                  = int(os.getenv('PORT', 5000))

    # Google credentials / sheet settings
    GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    GOOGLE_SHEET_TITLE      = os.getenv('GOOGLE_SHEET_TITLE', 'Jirago Ops')
    CATALOGUE_TAB           = os.getenv('CATALOGUE_TAB', 'Catalogue')
    ORDERS_TAB              = os.getenv('ORDERS_TAB', 'Orders_Status')

    # Catalogue file fallback (rarely used now—most loads from Sheets)
    CATALOGUE_FILE = os.getenv('CATALOGUE_FILE', 'catalogue_master.csv')
