# tests/test_whatsapp.py
import pytest
from app.services import whatsapp

def test_parse_order_message_valid():
    data = {
        "Body": "Order: 10 bags of cement",
        "From": "+911234567890"
    }
    order_data = whatsapp.parse_order_message(data)
    assert order_data["customer"] == "+911234567890"
    assert "cement" in order_data["order_message"]

def test_parse_order_message_missing_fields():
    data = {"Body": "", "From": ""}
    with pytest.raises(ValueError):
        whatsapp.parse_order_message(data)
