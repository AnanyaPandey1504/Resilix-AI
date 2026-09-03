from datetime import datetime, timezone

# Simple in-memory mock storage for Promise-To-Pay
_PTP_STORE = {}

def record_promise_to_pay(event_id: str, customer_phone: str, promised_date_iso: str) -> dict:
    """Records a PTP date for a specific event/customer."""
    _PTP_STORE[event_id] = {
        "customer_phone": customer_phone,
        "promised_date_iso": promised_date_iso,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    }
    return {
        "status": "PTP_RECORDED_OUTREACH_SUPPRESSED",
        "promised_date": promised_date_iso
    }

def is_outreach_suppressed(event_id: str, current_dt_utc: datetime = None) -> bool:
    """Returns True if the current date is before the promised date."""
    if event_id not in _PTP_STORE:
        return False
        
    if current_dt_utc is None:
        current_dt_utc = datetime.now(timezone.utc)
        
    promised_date_iso = _PTP_STORE[event_id]["promised_date_iso"]
    try:
        promised_date = datetime.fromisoformat(promised_date_iso)
        if promised_date.tzinfo is None:
            promised_date = promised_date.replace(tzinfo=timezone.utc)
            
        if current_dt_utc < promised_date:
            return True
    except ValueError:
        pass
        
    return False
