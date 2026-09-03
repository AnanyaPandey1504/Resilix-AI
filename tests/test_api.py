import pytest
from fastapi.testclient import TestClient
import hmac
import hashlib
import json
from unittest.mock import patch

from app.main import app, startup_event
from app.db.crypto_ledger import get_db_connection

client = TestClient(app)

# Ensure DB is initialized
startup_event()

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup: clear the table to ensure clean state
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recovery_audit_log')
    conn.commit()
    conn.close()
    yield
    # Teardown logic if needed

def generate_signature(payload_bytes: bytes, secret: str = "test_secret") -> str:
    return hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

@patch('app.services.razorpay_client.settings.RAZORPAY_WEBHOOK_SECRET', 'test_secret')
def test_valid_webhook_signature():
    payload = {
        "event": "payment.failed",
        "id": "event_123",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_123",
                    "amount": 10000,
                    "contact": "9999999999",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment failed"
                }
            }
        }
    }
    body_bytes = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body_bytes)
    
    response = client.post(
        "/webhooks/razorpay",
        content=body_bytes,
        headers={"X-Razorpay-Signature": signature}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "event_123"
    assert "status" in data
    assert data["amount_inr"] == 100.0

@patch('app.services.razorpay_client.settings.RAZORPAY_WEBHOOK_SECRET', 'test_secret')
def test_invalid_webhook_signature():
    payload = {"event": "payment.failed", "id": "event_456"}
    body_bytes = json.dumps(payload).encode('utf-8')
    
    response = client.post(
        "/webhooks/razorpay",
        content=body_bytes,
        headers={"X-Razorpay-Signature": "invalid_signature"}
    )
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"

@patch('app.services.razorpay_client.settings.RAZORPAY_WEBHOOK_SECRET', 'test_secret')
def test_idempotency():
    payload = {
        "event": "payment.failed",
        "id": "event_duplicate",
        "payload": {
            "payment": {
                "entity": {
                    "amount": 50000,
                    "contact": "8888888888",
                    "error_code": "NETWORK_ERROR"
                }
            }
        }
    }
    body_bytes = json.dumps(payload).encode('utf-8')
    signature = generate_signature(body_bytes)
    
    # First call
    response1 = client.post(
        "/webhooks/razorpay",
        content=body_bytes,
        headers={"X-Razorpay-Signature": signature}
    )
    assert response1.status_code == 200
    
    # Second call
    response2 = client.post(
        "/webhooks/razorpay",
        content=body_bytes,
        headers={"X-Razorpay-Signature": signature}
    )
    assert response2.status_code == 200
    data = response2.json()
    assert data["status"] == "ALREADY_PROCESSED"
    assert data["event_id"] == "event_duplicate"

def test_get_metrics():
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_events_processed" in data
    assert "ledger_status" in data
    assert data["ledger_status"]["is_valid"] is True

def test_get_dashboard():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PulseRecover // Enterprise" in response.text

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "PulseRecover-Pro"}

def test_api_simulate():
    payload = {
        "event_id": "sim_123",
        "error_code": "503",
        "error_description": "Gateway Error",
        "amount_inr": 1500.0,
        "customer_phone": "9999999999"
    }
    
    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == "sim_123"
    assert data["cohort"] == "TECHNICAL_DOWNTIME"
    assert data["action_taken"] == "SILENT_RETRY_QUEUED"
