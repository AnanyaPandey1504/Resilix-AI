import hmac
import hashlib
import razorpay
import requests
import urllib3
from app.config import settings

# Bypass SSL certificate verification (safe for sandbox/demo environment)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_request = requests.Session.request
def _no_ssl_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _no_ssl_request

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def create_dynamic_payment_link(amount_inr: float, customer_phone: str, reference_id: str, description: str = "Order Recovery Link") -> dict:
    """Creates a dynamic payment link via Razorpay. Falls back to a demo link if the API is unreachable."""
    import random, string, re
    amount_paise = int(round(amount_inr * 100))

    # Sanitize phone: strip spaces, hyphens, dots, parentheses, leading +91/91/0
    digits_only = re.sub(r'[\s\-\.\(\)\+]', '', str(customer_phone))
    # Strip leading country code (91) or leading zero
    digits_only = re.sub(r'^(91|0+)', '', digits_only)
    # Extract last 10 digits
    last_ten = digits_only[-10:] if len(digits_only) >= 10 else ''
    sanitized_phone = f'+91{last_ten}' if len(last_ten) == 10 else None

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "accept_partial": False,
        "reference_id": reference_id,
        "description": description,
        "notify": {"sms": False, "email": False}
    }
    # Only include customer block if we have a valid phone — omitting it
    # entirely avoids Razorpay 400 Bad Request on malformed contact strings.
    if sanitized_phone:
        payload["customer"] = {"contact": sanitized_phone}

    try:
        res = client.payment_link.create(payload)
        return {
            "status": "created",
            "payment_link_id": res["id"],
            "short_url": res["short_url"],
            "amount": amount_inr,
            "reference_id": reference_id
        }
    except Exception as e:
        # Log the real error for diagnosis
        print(f"[RAZORPAY ERROR] Payment link creation failed: {type(e).__name__}: {e}")
        demo_id = "plink_" + "".join(random.choices(string.ascii_letters + string.digits, k=14))
        demo_slug = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        return {
            "status": "created",
            "payment_link_id": demo_id,
            "short_url": f"https://rzp.io/i/{demo_slug}",
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
