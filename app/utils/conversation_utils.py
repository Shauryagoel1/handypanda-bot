from collections import defaultdict
from datetime import datetime
import re
import logging
from flask import current_app

# Simple in-memory store for conversation state
# In production, you'd want to use Redis or a database
conversation_state = defaultdict(dict)

class MessageParser:
    GREETINGS = {'hi', 'hello', 'hey', 'hii', 'hiii', 'hiiii', 'helo', 'hllo', 'hola'}
    YES_RESPONSES = {'yes', 'yeah', 'yep', 'sure', 'ok', '1'}
    NO_RESPONSES = {'no', 'nope', 'no thanks', 'nah', '2'}
    COD_RESPONSES = {'cod', 'cash', 'cash on delivery', '1'}
    UPI_RESPONSES = {'upi', 'online', 'gpay', 'google pay', 'phonepe', '2'}

    @staticmethod
    def normalize_message(message: str) -> str:
        """Normalize message for consistent parsing"""
        return message.strip().lower()

    @staticmethod
    def is_greeting(message: str) -> bool:
        """Check if message is a greeting"""
        return message in MessageParser.GREETINGS

    @staticmethod
    def is_yes_response(message: str) -> bool:
        """Check if message is an affirmative response"""
        return message in MessageParser.YES_RESPONSES

    @staticmethod
    def is_no_response(message: str) -> bool:
        """Check if message is a negative response"""
        return message in MessageParser.NO_RESPONSES

    @staticmethod
    def is_cod_response(message: str) -> bool:
        """Check if message indicates Cash on Delivery"""
        return message in MessageParser.COD_RESPONSES

    @staticmethod
    def is_upi_response(message: str) -> bool:
        """Check if message indicates UPI payment"""
        return message in MessageParser.UPI_RESPONSES

    @staticmethod
    def extract_quantity(message: str) -> str:
        """Extract quantity from message, default to 1 if not found"""
        qty_match = re.search(r'(\d+)\s*(?:pc|pcs|pieces?|units?)?\b', message, re.I)
        return qty_match.group(1) if qty_match else "-1"

    @staticmethod
    def is_order_id_response(message: str) -> tuple[bool, str]:
        """Check if message is an order ID response and extract the ID"""
        if message.startswith("order id-"):
            return True, message.split("order id-")[-1].strip()
        return False, ""

    @staticmethod
    def is_valid_query(message: str) -> bool:
        """Check if message is a valid product query"""
        words = message.split()
        return len(words) >= 2 or any(char.isdigit() for char in message)

class ConversationManager:
    def __init__(self, user_phone: str):
        self.user_phone = user_phone

    def get_current_sku(self) -> str | None:
        """Get the current SKU ID for the user"""
        state = conversation_state.get(self.user_phone, {})
        return state.get('last_sku')

    def set_current_sku(self, sku_id: str) -> None:
        """Set the current SKU ID for the user"""
        conversation_state[self.user_phone] = {
            'last_sku': sku_id,
            'timestamp': datetime.now().isoformat()
        }

    def clear_state(self) -> None:
        """Clear the conversation state for the user"""
        if self.user_phone in conversation_state:
            del conversation_state[self.user_phone]

    def has_active_conversation(self) -> bool:
        """Check if user has an active conversation with a product context"""
        return self.user_phone in conversation_state and 'last_sku' in conversation_state[self.user_phone]

class MessageFormatter:
    @staticmethod
    def format_greeting() -> str:
        return "👋 Hi! What plumbing item do you need?\nExample: 2 pieces bend"

    @staticmethod
    def format_clarification() -> str:
        return "🤔 Please specify item and quantity.\nExample: 2 pieces bend"

    @staticmethod
    def format_no_matches() -> str:
        return "🔍 No matching items found. Please try again."

    @staticmethod
    def format_error_response() -> str:
        return "❌ Something went wrong. Please try again."

    @staticmethod
    def format_order_error() -> str:
        return "❌ Order processing failed. Please try again."

    @staticmethod
    def format_no_thanks() -> str:
        return "👍 Got it. Let me know if you need anything else!"

    @staticmethod
    def format_product_response(product: dict) -> tuple[str, list[str]]:
        """Format product details and return message and buttons"""
        body_text = (
            f"✨ Found: {product['brand']} {product['name']}\n"
            f"📦 Size: {product['size_text']}\n"
            f"💰 Price: ₹{product['price']}/{product['price_unit']}\n\n"
            "Would you like to place order?"
        )
        buttons = ["Yes", "No"]
        return body_text, buttons

    @staticmethod
    def format_payment_options() -> tuple[str, list[str]]:
        """Format payment options message"""
        body_text = "Choose payment method:"
        buttons = ["Cash on Delivery", "UPI"]
        return body_text, buttons

    @staticmethod
    def format_cod_confirmation() -> str:
        return "✅ Order confirmed! We'll contact you for delivery details."

    @staticmethod
    def format_upi_payment_instructions() -> str:
        upi_number = current_app.config['UPI_NUMBER']
        return (
            f"Pay using UPI: {upi_number}@upi\n"
            "Send payment screenshot for quick verification."
        ) 