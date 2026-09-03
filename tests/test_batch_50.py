import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, startup_event
from app.db.crypto_ledger import get_db_connection, verify_ledger

client = TestClient(app)

# Ensure DB is initialized
startup_event()

@pytest.fixture(autouse=True)
def setup_teardown():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recovery_audit_log')
    conn.commit()
    conn.close()
    yield

@patch('app.engine.state_machine.resilient_create_payment_link')
@patch('app.engine.mandate_rescue.create_subscription_registration_link')
@patch('app.engine.receivables_chaser.resilient_create_payment_link')
def test_high_volume_50_scenario_benchmark(mock_b2b_link, mock_sub_link, mock_b_link):
    # Mock all external Razorpay calls for offline testing
    mock_b_link.return_value = {"status": "created", "id": "plink_123", "short_url": "https://rzp.io/i/123", "amount": 1000.0}
    mock_sub_link.return_value = {"status": "created", "subscription_id": "sub_123", "short_url": "https://rzp.io/i/sub123"}
    mock_b2b_link.return_value = {"status": "created", "id": "plink_b2b", "short_url": "https://rzp.io/i/b2b", "amount": 49000.0}

    events = []
    
    # 15x Rail A (Technical Downtime)
    for i in range(15):
        events.append({
            "event_id": f"batch_A_{i}",
            "error_code": "503",
            "error_description": "Bank Internal Error",
            "amount_inr": 1500.0 + i * 10,
            "customer_phone": f"99999990{i:02d}"
        })
        
    # 15x Rail B (Consumer Drop-offs)
    for i in range(15):
        events.append({
            "event_id": f"batch_B_{i}",
            "error_code": "ABORTED",
            "error_description": "User closed window",
            "amount_inr": 800.0 + i * 5,
            "customer_phone": f"88888880{i:02d}"
        })
        
    # 10x Rail C (Mandate Degradations)
    for i in range(10):
        events.append({
            "event_id": f"batch_C_{i}",
            "error_code": "MANDATE_DEGRADED",
            "error_description": "Insufficient Funds",
            "amount_inr": 499.0 + i,
            "customer_phone": f"77777770{i:02d}"
        })
        
    # 10x Rail D (B2B Receivables)
    for i in range(10):
        events.append({
            "event_id": f"batch_D_{i}",
            "error_code": "INVOICE_OVERDUE",
            "error_description": "Net-30 Overdue",
            "amount_inr": 50000.0 + i * 1000,
            "customer_phone": f"66666660{i:02d}"
        })
        
    assert len(events) == 50
    
    # Execute sequentially
    for payload in events:
        response = client.post("/api/simulate", json=payload)
        assert response.status_code == 200, f"Event {payload['event_id']} failed"
        
        data = response.json()
        assert "action_taken" in data
        assert "ledger_hash" in data
        
    # Check metrics
    metrics_res = client.get("/api/metrics")
    assert metrics_res.status_code == 200
    metrics_data = metrics_res.json()
    
    assert metrics_data["total_events_processed"] == 50
    
    # Assert ledger valid
    ledger_status = verify_ledger()
    assert ledger_status["is_valid"] is True
    assert ledger_status["total_records"] == 50
    assert ledger_status["broken_at_event_id"] is None
