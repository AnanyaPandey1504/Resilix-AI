from app.engine.ptp_tracker import record_promise_to_pay
from app.engine.failure_resilience import resilient_create_payment_link

def handle_b2b_receivable(event_id: str, amount_inr: float, customer_phone: str, promised_date_iso: str | None = None) -> dict:
    """
    Handles B2B overdue receivables. Applies a 2% settlement discount unless a PTP date is provided.
    """
    if promised_date_iso:
        return record_promise_to_pay(event_id, customer_phone, promised_date_iso)
        
    discounted_amount = round(amount_inr * 0.98, 2)
    
    link_res = resilient_create_payment_link(
        amount_inr=discounted_amount,
        customer_phone=customer_phone,
        reference_id=f"b2b_{event_id}",
        description="B2B Early Settlement Discount Link (2% Off)"
    )
    
    # Check if the resilient link was deferred
    if link_res.get("status") == "DEFERRED_UPSTREAM_LATENCY":
        return link_res
        
    return {
        "status": "B2B_DISCOUNT_LINK_CREATED",
        "customer_phone": customer_phone,
        "original_amount": amount_inr,
        "discounted_amount": discounted_amount,
        "link_data": link_res
    }
