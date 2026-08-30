import pytest
import sqlite3
import uuid
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.db.crypto_ledger import append_audit_record, verify_ledger, get_db_connection
from app.engine.guardians import (
    check_trai_quiet_hours,
    check_rbi_mandate_notice,
    check_high_value_gate,
    check_stopping_rules
)
from app.config import settings

@pytest.fixture(autouse=True)
def clean_db():
    # Make sure we use a clean DB for tests
    if os.path.exists(settings.DB_PATH):
        os.remove(settings.DB_PATH)
    # Re-initialize table
    from app.db.crypto_ledger import init_db
    init_db()
    yield
    if os.path.exists(settings.DB_PATH):
        os.remove(settings.DB_PATH)

def test_ledger_integrity():
    # Verify empty ledger
    res = verify_ledger()
    assert res["is_valid"] is True
    assert res["total_records"] == 0
    
    # Append sequential records
    append_audit_record("evt_1", "INSUFFICIENT_FUNDS", "SEND_EMAIL", {"amount": 100})
    append_audit_record("evt_2", "INSUFFICIENT_FUNDS", "SEND_SMS", {"amount": 200})
    
    res = verify_ledger()
    assert res["is_valid"] is True
    assert res["total_records"] == 2
    assert res["broken_at_id"] is None

def test_ledger_tampering():
    append_audit_record("evt_1", "INSUFFICIENT_FUNDS", "SEND_EMAIL", {"amount": 100})
    append_audit_record("evt_2", "INSUFFICIENT_FUNDS", "SEND_SMS", {"amount": 200})
    append_audit_record("evt_3", "INSUFFICIENT_FUNDS", "WHATSAPP", {"amount": 300})
    
    res = verify_ledger()
    assert res["is_valid"] is True
    
    # Tamper with the database explicitly
    conn = get_db_connection()
    cursor = conn.cursor()
    # Change the action taken in the second row
    cursor.execute("UPDATE recovery_audit_log SET action_taken = 'VOICE_CALL' WHERE event_id = 'evt_2'")
    conn.commit()
    conn.close()
    
    # Verify tampering is caught
    res = verify_ledger()
    assert res["is_valid"] is False
    # row_id 2 should be the broken one since its hash will not match the computed hash of the modified data
    assert res["broken_at_id"] == 2

def test_check_trai_quiet_hours():
    ist = ZoneInfo("Asia/Kolkata")
    # 11:00 PM IST (23:00) -> Should be blocked
    dt_blocked = datetime(2023, 10, 1, 23, 0, 0, tzinfo=ist)
    valid, reason = check_trai_quiet_hours(dt_blocked)
    assert valid is False
    assert reason == "TRAI_QUIET_HOURS_DEFERRED_TO_0801_AM"
    
    # 2:00 PM IST (14:00) -> Should be allowed
    dt_allowed = datetime(2023, 10, 1, 14, 0, 0, tzinfo=ist)
    valid, reason = check_trai_quiet_hours(dt_allowed)
    assert valid is True
    assert reason == "ALLOWED"

def test_check_rbi_mandate_notice():
    utc = timezone.utc
    execution_time = datetime(2023, 10, 2, 12, 0, 0, tzinfo=utc)
    
    # Pre-debit sent 12 hours prior -> blocked
    pre_debit_12h = execution_time - timedelta(hours=12)
    valid, reason = check_rbi_mandate_notice(pre_debit_12h, execution_time)
    assert valid is False
    assert reason == "RBI_24H_PRE_DEBIT_NOTICE_VIOLATION"
    
    # Pre-debit sent 25 hours prior -> allowed
    pre_debit_25h = execution_time - timedelta(hours=25)
    valid, reason = check_rbi_mandate_notice(pre_debit_25h, execution_time)
    assert valid is True
    assert reason == "ALLOWED"

def test_check_high_value_gate():
    # Exactly at threshold
    valid, reason = check_high_value_gate(15000.0)
    assert valid is True
    
    # Below threshold
    valid, reason = check_high_value_gate(10000.0)
    assert valid is True
    
    # Above threshold
    valid, reason = check_high_value_gate(25000.0)
    assert valid is False
    assert reason == "REQUIRES_HUMAN_MANAGER_APPROVAL"

def test_check_stopping_rules():
    # Touch count reaches 2
    valid, reason = check_stopping_rules(touch_count=2, user_opted_out=False)
    assert valid is False
    assert reason == "MAX_TOUCHES_EXCEEDED"
    
    # User opted out
    valid, reason = check_stopping_rules(touch_count=0, user_opted_out=True)
    assert valid is False
    assert reason == "USER_OPTED_OUT_CEASE_OUTREACH"
    
    # Allowed
    valid, reason = check_stopping_rules(touch_count=1, user_opted_out=False)
    assert valid is True
    assert reason == "ALLOWED"
