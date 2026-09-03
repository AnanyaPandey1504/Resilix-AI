from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def check_trai_quiet_hours(check_dt: datetime = None) -> tuple[bool, str]:
    ist = ZoneInfo("Asia/Kolkata")
    if check_dt is None:
        check_dt = datetime.now(ist)
    elif check_dt.tzinfo is None:
        check_dt = check_dt.replace(tzinfo=ist)
    else:
        check_dt = check_dt.astimezone(ist)
        
    hour = check_dt.hour
    if hour >= 21 or hour < 9:
        return (False, "TRAI_QUIET_HOURS_DEFERRED_TO_0801_AM")
    return (True, "ALLOWED")

def check_rbi_mandate_notice(pre_debit_sent_at: datetime | None, execution_time: datetime = None) -> tuple[bool, str]:
    if execution_time is None:
        execution_time = datetime.now(timezone.utc)
        
    if pre_debit_sent_at is None:
        return (False, "RBI_24H_PRE_DEBIT_NOTICE_VIOLATION")
        
    # Ensure both are timezone aware
    if execution_time.tzinfo is None:
        execution_time = execution_time.replace(tzinfo=timezone.utc)
    if pre_debit_sent_at.tzinfo is None:
        pre_debit_sent_at = pre_debit_sent_at.replace(tzinfo=timezone.utc)
        
    delta = (execution_time - pre_debit_sent_at).total_seconds()
    if delta < 86400:
        return (False, "RBI_24H_PRE_DEBIT_NOTICE_VIOLATION")
        
    return (True, "ALLOWED")

def check_high_value_gate(amount_inr: float) -> tuple[bool, str]:
    if amount_inr > 15000.0:
        return (False, "REQUIRES_HUMAN_MANAGER_APPROVAL")
    return (True, "ALLOWED")

def check_stopping_rules(touch_count: int, user_opted_out: bool = False) -> tuple[bool, str]:
    if user_opted_out:
        return (False, "USER_OPTED_OUT_CEASE_OUTREACH")
    if touch_count >= 2:
        return (False, "MAX_TOUCHES_EXCEEDED")
    return (True, "ALLOWED")
