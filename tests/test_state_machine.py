import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from app.engine.state_machine import process_recovery_event
from app.db.crypto_ledger import verify_ledger

@pytest.fixture(autouse=True)
def clean_ledger():
    import sqlite3
    from app.config import settings
    from app.db.crypto_ledger import init_db
    
    # Ensure table exists
    init_db()
    
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recovery_audit_log')
    conn.commit()
    conn.close()
    yield
    
def test_bank_503_routes_to_silent_retry():
    res = process_recovery_event(
        event_id="evt_503",
        error_code="503",
        error_description="Gateway Error",
        amount_inr=1000.0,
        customer_phone="9999999999"
    )
    assert res["cohort"] == "TECHNICAL_DOWNTIME"
    assert res["action_taken"] == "SILENT_RETRY_QUEUED"
    assert res["status"] == "SILENT_RETRY_QUEUED"

@patch('app.engine.state_machine.resilient_create_payment_link')
def test_daytime_consumer_drop_generates_link(mock_link):
    mock_link.return_value = {"status": "created", "id": "plink_123"}
    ist = ZoneInfo("Asia/Kolkata")
    daytime = datetime(2026, 1, 1, 14, 0, 0, tzinfo=ist) # 2:00 PM IST
    
    res = process_recovery_event(
        event_id="evt_drop_day",
        error_code="ABORTED",
        error_description="User closed window",
        amount_inr=1000.0,
        customer_phone="9999999999",
        check_dt_ist=daytime
    )
    assert res["cohort"] == "CONSUMER_CHECKOUT_DROP"
    assert res["action_taken"] == "DYNAMIC_LINK_SENT"
    assert res["status"] == "DYNAMIC_LINK_SENT"
    assert "copy" in res["details"]

def test_quiet_hours_consumer_drop_defers():
    ist = ZoneInfo("Asia/Kolkata")
    nighttime = datetime(2026, 1, 1, 23, 0, 0, tzinfo=ist) # 11:00 PM IST
    
    res = process_recovery_event(
        event_id="evt_drop_night",
        error_code="ABORTED",
        error_description="User closed window",
        amount_inr=1000.0,
        customer_phone="9999999999",
        check_dt_ist=nighttime
    )
    assert res["cohort"] == "CONSUMER_CHECKOUT_DROP"
    assert res["action_taken"] == "DEFERRED_TRAI_QUIET_HOURS"
    assert res["status"] == "DEFERRED_TRAI_QUIET_HOURS"

@patch('app.engine.mandate_rescue.create_subscription_registration_link')
def test_mandate_degradation_success_and_block(mock_sub_link):
    mock_sub_link.return_value = {"id": "sub_123"}
    
    # 1. Failure - No notice
    res1 = process_recovery_event(
        event_id="evt_mandate_fail",
        error_code="MANDATE_DEGRADED",
        error_description="Failed",
        amount_inr=500.0,
        customer_phone="9999999999",
        pre_debit_sent_at=None
    )
    assert res1["action_taken"] == "BLOCKED_BY_GUARDIAN"
    
    # 2. Success - Valid notice sent > 24h ago
    valid_notice = datetime.now(timezone.utc) - timedelta(hours=25)
    res2 = process_recovery_event(
        event_id="evt_mandate_success",
        error_code="MANDATE_DEGRADED",
        error_description="Failed",
        amount_inr=500.0,
        customer_phone="9999999999",
        pre_debit_sent_at=valid_notice
    )
    assert res2["action_taken"] == "UPI_AUTOPAY_MIGRATION_LINK_CREATED"

@patch('app.engine.receivables_chaser.resilient_create_payment_link')
def test_b2b_overdue_discount_and_ptp(mock_link):
    mock_link.return_value = {"status": "created", "id": "plink_b2b"}
    
    # 1. With PTP
    res1 = process_recovery_event(
        event_id="evt_b2b_ptp",
        error_code="INVOICE_OVERDUE",
        error_description="Overdue",
        amount_inr=5000.0,
        customer_phone="9999999999",
        promised_date_iso="2026-12-31T00:00:00Z"
    )
    assert res1["action_taken"] == "PTP_RECORDED_OUTREACH_SUPPRESSED"
    
    # 2. Without PTP -> 2% discount (5000 * 0.98 = 4900)
    res2 = process_recovery_event(
        event_id="evt_b2b_discount",
        error_code="INVOICE_OVERDUE",
        error_description="Overdue",
        amount_inr=5000.0,
        customer_phone="9999999999"
    )
    assert res2["action_taken"] == "B2B_DISCOUNT_LINK_CREATED"
    assert res2["details"]["discounted_amount"] == 4900.0
    mock_link.assert_called_once()
    assert mock_link.call_args[1]["amount_inr"] == 4900.0

def test_high_value_transaction_gate():
    res = process_recovery_event(
        event_id="evt_hv",
        error_code="ABORTED",
        error_description="Failed",
        amount_inr=20000.0,
        customer_phone="9999999999"
    )
    assert res["status"] == "BLOCKED_BY_GUARDIAN"
    assert res["details"]["reason"] == "REQUIRES_HUMAN_MANAGER_APPROVAL"

def test_crypto_ledger_validity():
    process_recovery_event("evt_l1", "503", "Gateway", 100.0, "99")
    process_recovery_event("evt_l2", "ABORTED", "Drop", 200.0, "99", check_dt_ist=datetime(2026,1,1,23,0,0,tzinfo=ZoneInfo("Asia/Kolkata")))
    
    verify_result = verify_ledger()
    assert verify_result["is_valid"] is True
    assert verify_result["total_records"] >= 2
