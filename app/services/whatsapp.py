# app/services/whatsapp.py
def parse_order_message(data: dict) -> dict:
    """
    Expected input (from Twilio Sandbox) might use keys like:
      - "Body": the text of the message
      - "From": the sender's number
    """
    if not data:
        raise ValueError("Empty payload received.")
    
    # Using keys typically returned by Twilio for WhatsApp messages
    # print(data)
    order_message = data.get("Body") or data.get("message")
    # print(order_message)
    customer = data.get("From") or data.get("from")
    # print(customer)
    
    if not order_message or not customer:
        raise ValueError("Missing required fields: 'message' and/or 'from'.")
    
    return {
        "customer": customer,
        "order_message": order_message,
        "timestamp": data.get("timestamp")
    }