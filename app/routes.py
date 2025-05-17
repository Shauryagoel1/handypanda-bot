# File: app/routes.py
from flask import Blueprint, request, Response
from datetime import datetime
import re

from twilio.twiml.messaging_response import MessagingResponse
from app.services.catalogue import enhanced_search
from app.services import sheets

main_bp = Blueprint('main', __name__)

# -------------------------------------------------
# Helper to add quick-reply buttons
# -------------------------------------------------
def send_quick_reply(resp, body_text, button_texts):
    msg = resp.message(body_text)
    msg._msg['persistentAction'] = [f"reply {b}" for b in button_texts]


# -------------------------------------------------
# Webhook
# -------------------------------------------------
@main_bp.route('/webhook', methods=['POST'])
def webhook():
    data        = request.get_json() or request.form.to_dict()
    user_msg    = data.get('Body', '')
    user_phone  = data.get('From', '')

    resp = MessagingResponse()

    # ---------- Button taps ----------
    if user_msg.startswith("Order ID-"):
        sku_id = user_msg.split("Order ID-")[-1].strip()
        sheets.update_status(user_phone, sku_id, "Awaiting Payment")

        # 🔮 Future: QR media.  For now, plain link reply
        pay_url = f"https://pay.example.com/{sku_id}"
        resp.message(f"Thank you! Please complete payment here:\n{pay_url}")
        return Response(str(resp), mimetype='application/xml')

    if re.match(r'^no thanks$', user_msg, re.I):
        resp.message("No problem. Let me know if you need anything else!")
        return Response(str(resp), mimetype='application/xml')

    # ---------- Product search ----------
    matches = enhanced_search(user_msg, top_n=3)
    if not matches:
        resp.message("Sorry, couldn’t find matching items.")
        return Response(str(resp), mimetype='application/xml')

    best = matches[0]
    body = (f"I found *{best['brand']} {best['name']}* "
            f"({best['size_text']}) — ₹{best['price']}/{best['price_unit']}. "
            f"Would you like to order?")
    send_quick_reply(resp, body, [f"Order ID-{best['id']}", "No thanks"])

    # ---------- Log draft order ----------
    sheets.append_order({
        "Timestamp": datetime.now().isoformat(),
        "Phone": user_phone,
        "Query": user_msg,
        "SKU_ID": best['id'],
        "Qty": "?",
        "Status": "Awaiting Confirm"
    })

    return Response(str(resp), mimetype='application/xml')
