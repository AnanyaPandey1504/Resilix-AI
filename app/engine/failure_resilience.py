from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import razorpay
from app.services.razorpay_client import create_dynamic_payment_link

def handle_retry_error(retry_state):
    """Callback for tenacity when all retries are exhausted."""
    err = retry_state.outcome.exception()
    # Find reference_id in args or kwargs
    reference_id = None
    if retry_state.args and len(retry_state.args) >= 3:
        reference_id = retry_state.args[2]
    elif 'reference_id' in retry_state.kwargs:
        reference_id = retry_state.kwargs['reference_id']

    return {
        "status": "DEFERRED_UPSTREAM_LATENCY",
        "action": "QUEUED_FOR_ASYNC_RECOVERY",
        "error": str(err),
        "reference_id": reference_id
    }

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, razorpay.errors.ServerError, razorpay.errors.BadRequestError)),
    retry_error_callback=handle_retry_error
)
def resilient_create_payment_link(amount_inr: float, customer_phone: str, reference_id: str, description: str = "Order Recovery Link") -> dict:
    """
    Executes create_dynamic_payment_link wrapped with retry logic catching ConnectionError,
    TimeoutError, and razorpay.errors.ServerError / BadRequestError.
    """
    return create_dynamic_payment_link(amount_inr, customer_phone, reference_id, description)
