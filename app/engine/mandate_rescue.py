from datetime import datetime
from app.services.razorpay_client import create_subscription_registration_link

def handle_mandate_rescue(event_id: str, customer_phone: str, plan_id: str, pre_debit_sent_at: datetime | None) -> dict:
    """
    Generates a UPI Autopay migration link.
    (RBI compliance is now enforced in the centralized state machine).
    """
    link_res = create_subscription_registration_link(
        customer_phone=customer_phone,
        plan_id=plan_id,
        reference_id=f"rescue_{event_id}"
    )
    
    return {
        "status": "UPI_AUTOPAY_MIGRATION_LINK_CREATED",
        "customer_phone": customer_phone,
        "link_data": link_res
    }
