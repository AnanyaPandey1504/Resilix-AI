import json
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.db.crypto_ledger import init_db, verify_ledger, get_db_connection
from app.services.razorpay_client import verify_webhook_signature
from app.engine.state_machine import process_recovery_event

app = FastAPI(title="PulseRecover Pro - Track 03")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup_event():
    init_db()

class SimulationRequest(BaseModel):
    event_id: str
    error_code: str
    error_description: str
    amount_inr: float
    customer_phone: str
    promised_date_iso: Optional[str] = None
    check_dt_ist: Optional[str] = None

@app.post("/api/simulate")
def simulate_event(req: SimulationRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM recovery_audit_log WHERE event_id = ?', (req.event_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"status": "ALREADY_PROCESSED", "event_id": req.event_id}
        
    response = process_recovery_event(
        event_id=req.event_id,
        error_code=req.error_code,
        error_description=req.error_description,
        amount_inr=req.amount_inr,
        customer_phone=req.customer_phone,
        promised_date_iso=req.promised_date_iso
    )
    return response

@app.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None)
):
    if not x_razorpay_signature:
        raise HTTPException(status_code=401, detail="Missing signature")
        
    body_bytes = await request.body()
    
    if not verify_webhook_signature(body_bytes, x_razorpay_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    event_type = payload.get("event", "")
    
    # Try to extract event ID from different possible payload structures
    payload_id = payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
    event_id = payload.get("id") or payload_id
    
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event_id")
        
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    amount_paise = entity.get("amount", 0)
    amount_inr = amount_paise / 100.0
    
    customer_phone = entity.get("contact", "")
    error_code = entity.get("error_code", "")
    error_description = entity.get("error_description", "")
    
    # Idempotency Check
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM recovery_audit_log WHERE event_id = ?', (event_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"status": "ALREADY_PROCESSED", "event_id": event_id}
        
    response = process_recovery_event(
        event_id=event_id,
        error_code=error_code,
        error_description=error_description,
        amount_inr=amount_inr,
        customer_phone=customer_phone
    )
    
    return response

@app.get("/api/metrics")
def get_metrics():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM recovery_audit_log ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    total_events_processed = len(rows)
    total_gmv_at_risk = 0.0
    total_gmv_recovered = 0.0
    
    silent_retries = 0
    dynamic_links = 0
    mandate_migrations = 0
    b2b_overdue = 0
    high_value_holds = 0
    
    recent_events = []
    
    for idx, row in enumerate(rows):
        payload_dict = json.loads(row["payload_json"])
        action = row["action_taken"]
        cohort = row["failure_cohort"]
        
        amount = 0.0
        if "link_data" in payload_dict and "amount" in payload_dict["link_data"]:
            amount = payload_dict["link_data"]["amount"]
        elif "amount_inr" in payload_dict:
            amount = payload_dict["amount_inr"]
        elif "amount" in payload_dict:
            amount = payload_dict["amount"]
        else:
            # Fallback for metrics visualization
            amount = 1000.0
            
        total_gmv_at_risk += amount
        
        is_high_value = action in ['BLOCKED_BY_GUARDIAN', 'REQUIRES_HUMAN_APPROVAL'] and amount > 15000

        if cohort == 'B2B_RECEIVABLE_OVERDUE':
            b2b_overdue += 1
        elif is_high_value:
            high_value_holds += 1
        elif action == 'SILENT_RETRY_QUEUED' or cohort == 'TECHNICAL_DOWNTIME':
            silent_retries += 1
        elif cohort == 'MANDATE_DEGRADATION' or action == 'UPI_AUTOPAY_MIGRATED':
            mandate_migrations += 1
        elif action == 'DYNAMIC_LINK_SENT' or cohort == 'CONSUMER_CHECKOUT_DROP':
            dynamic_links += 1
                
        # Estimate recovered
        if action not in ["HALT_RECOVERY", "DEFERRED_TRAI_QUIET_HOURS", "DEFERRED_UPSTREAM_LATENCY"]:
            total_gmv_recovered += amount

        if idx < 15:
            recent_events.append({
                "event_id": row["event_id"],
                "cohort": cohort,
                "action_taken": action,
                "timestamp": row["timestamp"],
                "current_hash": row["current_hash"],
                "payload_raw": payload_dict
            })
            
    recovery_rate_pct = (total_gmv_recovered / total_gmv_at_risk * 100) if total_gmv_at_risk > 0 else 0.0
    
    ledger_status = verify_ledger()
    
    rail_breakdown = {
        "silent_retries": silent_retries,
        "dynamic_links": dynamic_links,
        "mandate_migrations": mandate_migrations,
        "b2b_overdue": b2b_overdue,
        "high_value_holds": high_value_holds
    }

    active_guardrails_count = 0
    latest_guardrails = {
        "TRAI_QUIET_HOURS": "SKIPPED - NOT APPLICABLE",
        "HIGH_VALUE_GATE": "SKIPPED - NOT APPLICABLE",
        "RBI_MANDATE": "SKIPPED - NOT APPLICABLE",
        "HARASSMENT_CAP": "SKIPPED - NOT APPLICABLE"
    }

    if recent_events:
        latest_payload = recent_events[0].get("payload_raw", {})
        if "guardrails" in latest_payload:
            latest_guardrails = latest_payload["guardrails"]
            for key, status in latest_guardrails.items():
                if status in ["ENFORCING", "TRIGGERED - BLOCKED"]:
                    active_guardrails_count += 1
    
    return {
        "total_events_processed": total_events_processed,
        "total_gmv_at_risk": round(total_gmv_at_risk, 2),
        "total_gmv_recovered": round(total_gmv_recovered, 2),
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "rail_breakdown": rail_breakdown,
        "ledger_status": ledger_status,
        "recent_events": recent_events,
        "active_guardrails_count": active_guardrails_count,
        "latest_guardrails": latest_guardrails
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "PulseRecover-Pro"}
