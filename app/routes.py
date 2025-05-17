# File: app/routes.py
from flask import Blueprint, request, Response
from datetime import datetime
import re
import traceback
import json
import sys
import logging

from twilio.twiml.messaging_response import MessagingResponse
from app.services.catalogue import enhanced_search
from app.services import sheets

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

# -------------------------------------------------
# Helper to send fake quick-reply buttons
# -------------------------------------------------
def send_quick_reply(resp, body_text, button_texts):
    """
    Sends a single message combining the body text and numbered options.
    """
    # Combine the main text and options into one message
    lines = [body_text] + [f"{idx}. {text}" for idx, text in enumerate(button_texts, start=1)]
    resp.message("\n".join(lines))

# -------------------------------------------------
# Webhook endpoint
# -------------------------------------------------
@main_bp.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("\n" + "="*50)
        logger.info("📥 WEBHOOK REQUEST RECEIVED")
        
        # Debug raw payload for visibility
        raw_data = request.get_data(as_text=True)
        logger.info(f"✅ RAW DATA: {raw_data}")
        
        # Parse incoming data (JSON or form-encoded)
        if request.is_json:
            logger.info("📝 Processing JSON data")
            data = request.get_json()
        else:
            logger.info("📝 Processing form data")
            data = request.form.to_dict()
        
        logger.info(f"📦 Parsed data: {json.dumps(data, indent=2)}")
        
        user_msg = data.get('Body', '').strip()
        user_phone = data.get('From', '')
        logger.info(f"📱 Phone: {user_phone}")
        logger.info(f"💬 Message: {user_msg}")

        # Log raw message
        sheets.log_message(user_phone, user_msg)

        resp = MessagingResponse()

        # ---------- Handle user confirmations ----------
        if user_msg.startswith("Order ID-"):
            try:
                logger.info("🔄 Processing order confirmation")
                sku_id = user_msg.split("Order ID-")[-1].strip()
                sheets.update_status(user_phone, sku_id, "Awaiting Payment")

                # Placeholder payment link
                pay_url = f"https://pay.example.com/{sku_id}"
                resp.message(f"Thank you! Please complete payment here:\n{pay_url}")
                return Response(str(resp), mimetype='application/xml')
            except Exception as e:
                logger.error(f"❌ Error updating order status: {str(e)}")
                logger.error(traceback.format_exc())
                resp.message("Sorry, there was an error processing your order. Please try again.")
                return Response(str(resp), mimetype='application/xml')

        if re.match(r'^no thanks$', user_msg, re.I):
            resp.message("No problem. Let me know if you need anything else!")
            return Response(str(resp), mimetype='application/xml')

        # ---------- Product search ----------
        logger.info("🔍 Searching for products")
        matches = enhanced_search(user_msg, top_n=3)
        if not matches:
            resp.message("Sorry, couldn't find matching items.")
            return Response(str(resp), mimetype='application/xml')

        # Choose best match and send options
        best = matches[0]
        logger.info(f"✨ Best match: {best['brand']} {best['name']}")
        
        body_text = (
            f"I found *{best['brand']} {best['name']}* "
            f"({best['size_text']}) — ₹{best['price']}/{best['price_unit']}. "
            "Would you like to order?"
        )
        buttons = [f"Order ID-{best['id']}", "No thanks"]
        send_quick_reply(resp, body_text, buttons)

        # ---------- Log draft order ----------
        try:
            logger.info("\n📝 Attempting to log draft order...")
            # Extract quantity from user message
            qty_match = re.search(r'(\d+)\s*(?:pc|pcs|pieces?|units?)?\b', user_msg, re.I)
            
            # Get quantity, defaulting to 1 if not specified
            qty = qty_match.group(1) if qty_match else "1"
            
            order_data = {
                "Timestamp": datetime.now().isoformat(),
                "Phone": user_phone,
                "Query": user_msg,
                "SKU_ID": best['id'],
                "Qty": qty,
                "Status": "Awaiting Confirm"
            }
            logger.info(f"📦 Order data to log: {json.dumps(order_data, indent=2)}")
            sheets.append_order(order_data)
            logger.info("✅ Draft order logged successfully")
        except Exception as e:
            logger.error(f"❌ Error logging draft order: {str(e)}")
            logger.error(traceback.format_exc())
            # Continue with response even if logging fails
            
        return Response(str(resp), mimetype='application/xml')
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}")
        logger.error(traceback.format_exc())
        resp = MessagingResponse()
        resp.message("Sorry, something went wrong. Please try again later.")
        return Response(str(resp), mimetype='application/xml')
