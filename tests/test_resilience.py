import pytest
from unittest.mock import patch, MagicMock
import hmac
import hashlib
import razorpay
from app.services.razorpay_client import create_dynamic_payment_link, verify_webhook_signature
from app.engine.failure_resilience import resilient_create_payment_link
from app.config import settings

def test_successful_link_generation():
    with patch('app.services.razorpay_client.client.payment_link.create') as mock_create:
        mock_create.return_value = {
            "id": "plink_1234567890",
            "short_url": "https://rzp.io/i/12345"
        }
        
        result = create_dynamic_payment_link(1500.0, "9876543210", "ref_001")
        
        assert result["status"] == "created"
        assert result["payment_link_id"] == "plink_1234567890"
        assert result["short_url"] == "https://rzp.io/i/12345"
        assert result["amount"] == 1500.0
        assert result["reference_id"] == "ref_001"
        
        mock_create.assert_called_once_with({
            "amount": 150000,
            "currency": "INR",
            "accept_partial": False,
            "reference_id": "ref_001",
            "description": "Order Recovery Link",
            "customer": {
                "contact": "9876543210"
            },
            "notify": {"sms": False, "email": False}
        })

def test_circuit_breaker_retries_and_defers():
    with patch('app.engine.failure_resilience.create_dynamic_payment_link') as mock_create:
        # Simulate ServerError on all 3 attempts
        mock_create.side_effect = razorpay.errors.ServerError("504 Gateway Timeout")
        
        result = resilient_create_payment_link(1500.0, "9876543210", "ref_002")
        
        assert mock_create.call_count == 3
        assert result["status"] == "DEFERRED_UPSTREAM_LATENCY"
        assert result["action"] == "QUEUED_FOR_ASYNC_RECOVERY"
        assert "504 Gateway Timeout" in result["error"]
        assert result["reference_id"] == "ref_002"

def test_webhook_signature_verification_success():
    payload_body = b'{"event":"payment.captured"}'
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    
    # Generate valid signature
    valid_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    assert verify_webhook_signature(payload_body, valid_signature) is True

def test_webhook_signature_verification_failure():
    payload_body = b'{"event":"payment.captured"}'
    invalid_signature = "invalid_signature_string"
    
    assert verify_webhook_signature(payload_body, invalid_signature) is False
