import hmac
import hashlib
import razorpay
from app.config import settings

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def create_dynamic_payment_link(amount_inr: float, customer_phone: str, reference_id: str, description: str = "Order Recovery Link") -> dict:
    """Creates a dynamic payment link via Razorpay."""
    amount_paise = int(round(amount_inr * 100))
    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "accept_partial": False,
        "reference_id": reference_id,
        "description": description,
        "customer": {
            "contact": customer_phone
        },
        "notify": {"sms": False, "email": False}
    }
    
    res = client.payment_link.create(payload)
    return {
        "status": "created",
        "payment_link_id": res["id"],
        "short_url": res["short_url"],
        "amount": amount_inr,
        "reference_id": reference_id
    }

def create_subscription_registration_link(customer_phone: str, plan_id: str, reference_id: str) -> dict:
    """Creates an authentic payment link or subscription authorization payload."""
    payload = {
        "plan_id": plan_id,
        "total_count": 12, # Assuming 12 months as an example or it could be dynamically set
        "customer_notify": 0,
        "notes": {
            "reference_id": reference_id,
            "customer_phone": customer_phone
        }
    }
    res = client.subscription.create(payload)
    return {
        "status": "created",
        "subscription_id": res["id"],
        "short_url": res["short_url"],
        "plan_id": plan_id,
        "reference_id": reference_id
    }

def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """Safely verifies HMAC SHA256 against settings.RAZORPAY_WEBHOOK_SECRET."""
    try:
        expected_signature = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            payload_body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature_header)
    except Exception:
        return False
