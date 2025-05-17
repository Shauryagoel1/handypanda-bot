# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    print("🔧 Loaded configuration:")
    print(f"GOOGLE_CREDENTIALS_FILE: {app.config.get('GOOGLE_CREDENTIALS_FILE')}")
    print(f"GOOGLE_SHEET_TITLE: {app.config.get('GOOGLE_SHEET_TITLE')}")
    print(f"CATALOGUE_TAB: {app.config.get('CATALOGUE_TAB')}")
    print(f"ORDERS_TAB: {app.config.get('ORDERS_TAB')}")
    app.run(debug=True)