# File: app/routes.py
from flask import Blueprint, request, Response
import traceback
import json
import sys
import logging
from datetime import datetime

from twilio.twiml.messaging_response import MessagingResponse
from app.services.catalogue import enhanced_search
from app.services import sheets
from app.utils.conversation_utils import MessageParser, ConversationManager, MessageFormatter

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
# Helper to send quick-reply buttons
# -------------------------------------------------
def send_quick_reply(resp, body_text, button_texts):
    """
    Sends a single message combining the body text and numbered options.
    Uses WhatsApp-friendly formatting with proper spacing and emojis.
    """
    # Format options with emojis and proper spacing
    options = [f"📎 {idx}. {text}" for idx, text in enumerate(button_texts, start=1)]
    
    # Combine with double line breaks for WhatsApp
    message_text = f"{body_text}\n\n" + "\n".join(options)
    
    logger.info(f"📤 Sending quick reply message: {message_text}")
    resp.message(message_text)

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
        
        # Initialize response and utilities
        resp = MessagingResponse()
        user_msg = MessageParser.normalize_message(data.get('Body', ''))
        user_phone = data.get('From', '')
        conversation = ConversationManager(user_phone)
        
        logger.info(f"📱 Phone: {user_phone}")
        logger.info(f"💬 Message: {user_msg}")

        # Log raw message
        sheets.log_message(user_phone, user_msg)

        # ---------- Handle greetings ----------
        if MessageParser.is_greeting(user_msg):
            conversation.clear_state()
            resp.message(MessageFormatter.format_greeting())
            logger.info(f"📤 Sending greeting response: {str(resp)}")
            return Response(str(resp), mimetype='application/xml')

        # ---------- Handle very short or unclear messages ----------
        if not MessageParser.is_valid_query(user_msg):
            # Check if this is a yes/no response to a previous product
            if conversation.has_active_conversation():
                if MessageParser.is_yes_response(user_msg):
                    try:
                        logger.info("🔄 Processing order confirmation")
                        # Instead of going straight to payment, show payment options
                        body_text, buttons = MessageFormatter.format_payment_options()
                        send_quick_reply(resp, body_text, buttons)
                        logger.info(f"📤 Sending payment options: {str(resp)}")
                        return Response(str(resp), mimetype='application/xml')
                    except Exception as e:
                        logger.error(f"❌ Error showing payment options: {str(e)}")
                        logger.error(traceback.format_exc())
                        resp.message(MessageFormatter.format_order_error())
                        logger.info(f"📤 Sending error response: {str(resp)}")
                        return Response(str(resp), mimetype='application/xml')
                elif MessageParser.is_no_response(user_msg):
                    conversation.clear_state()
                    resp.message(MessageFormatter.format_no_thanks())
                    logger.info(f"📤 Sending 'no thanks' response: {str(resp)}")
                    return Response(str(resp), mimetype='application/xml')
                elif MessageParser.is_cod_response(user_msg):
                    try:
                        logger.info("🔄 Processing COD order")
                        sku_id = conversation.get_current_sku()
                        sheets.update_status(user_phone, sku_id, "COD Confirmed")
                        resp.message(MessageFormatter.format_cod_confirmation())
                        conversation.clear_state()
                        logger.info(f"📤 Sending COD confirmation: {str(resp)}")
                        return Response(str(resp), mimetype='application/xml')
                    except Exception as e:
                        logger.error(f"❌ Error processing COD order: {str(e)}")
                        logger.error(traceback.format_exc())
                        resp.message(MessageFormatter.format_order_error())
                        return Response(str(resp), mimetype='application/xml')
                elif MessageParser.is_upi_response(user_msg):
                    try:
                        logger.info("🔄 Processing UPI payment request")
                        sku_id = conversation.get_current_sku()
                        sheets.update_status(user_phone, sku_id, "Awaiting UPI Payment")
                        resp.message(MessageFormatter.format_upi_payment_instructions())
                        conversation.clear_state()
                        logger.info(f"📤 Sending UPI instructions: {str(resp)}")
                        return Response(str(resp), mimetype='application/xml')
                    except Exception as e:
                        logger.error(f"❌ Error processing UPI payment request: {str(e)}")
                        logger.error(traceback.format_exc())
                        resp.message(MessageFormatter.format_order_error())
                        return Response(str(resp), mimetype='application/xml')

            resp.message(MessageFormatter.format_clarification())
            logger.info(f"📤 Sending clarification response: {str(resp)}")
            return Response(str(resp), mimetype='application/xml')

        # ---------- Handle legacy order ID responses ----------
        is_order_id, sku_id = MessageParser.is_order_id_response(user_msg)
        if is_order_id:
            try:
                logger.info("🔄 Processing order confirmation")
                sheets.update_status(user_phone, sku_id, "Awaiting Payment")
                resp.message(MessageFormatter.format_order_confirmation(sku_id))
                conversation.clear_state()
                logger.info(f"📤 Sending payment response: {str(resp)}")
                return Response(str(resp), mimetype='application/xml')
            except Exception as e:
                logger.error(f"❌ Error updating order status: {str(e)}")
                logger.error(traceback.format_exc())
                resp.message(MessageFormatter.format_order_error())
                logger.info(f"📤 Sending error response: {str(resp)}")
                return Response(str(resp), mimetype='application/xml')

        # ---------- Product search ----------
        logger.info("🔍 Searching for products")
        matches = enhanced_search(user_msg, top_n=3)
        if not matches:
            resp.message(MessageFormatter.format_no_matches())
            logger.info(f"📤 Sending no matches response: {str(resp)}")
            return Response(str(resp), mimetype='application/xml')

        # Choose best match and send options
        best = matches[0]
        logger.info(f"✨ Best match: {best['brand']} {best['name']}")
        
        # Store the SKU_ID in conversation state
        conversation.set_current_sku(best['id'])
        
        # Format and send response
        body_text, buttons = MessageFormatter.format_product_response(best)
        send_quick_reply(resp, body_text, buttons)

        # ---------- Log draft order ----------
        try:
            logger.info("\n📝 Attempting to log draft order...")
            qty = MessageParser.extract_quantity(user_msg)
            
            order_data = {
                "Timestamp": datetime.now().isoformat(),  # Use current timestamp
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
            
        logger.info(f"📤 Sending final response: {str(resp)}")
        return Response(str(resp), mimetype='application/xml')
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}")
        logger.error(traceback.format_exc())
        resp = MessagingResponse()
        resp.message(MessageFormatter.format_error_response())
        logger.info(f"📤 Sending error response: {str(resp)}")
        return Response(str(resp), mimetype='application/xml')
