import json
from contextlib import asynccontextmanager
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db.crypto_ledger import init_db, verify_ledger, get_db_connection, seed_demo_data
from app.services.razorpay_client import verify_webhook_signature
from app.engine.state_machine import process_recovery_event

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_demo_data()
    yield

def startup_event():
    init_db()
    seed_demo_data()

app = FastAPI(title="Resilix AI - Track 03", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
    if isinstance(response, dict):
        response["current_hash"] = response.get("ledger_hash", "0000000000000000")
        if "timestamp" not in response:
            from datetime import datetime, timezone
            response["timestamp"] = datetime.now(timezone.utc).isoformat()
    return response

@app.post("/api/simulate_hack")
def simulate_hack():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM recovery_audit_log ORDER BY id DESC LIMIT 2')
    rows = cursor.fetchall()
    
    if len(rows) < 2:
        conn.close()
        process_recovery_event("seed_hack_01", "503", "Bank Error", 1500.0, "9876543210")
        process_recovery_event("seed_hack_02", "ABORTED", "Cart Drop", 2500.0, "9876543210")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM recovery_audit_log ORDER BY id DESC LIMIT 2')
        rows = cursor.fetchall()
        
    target_row = rows[1]
    payload = json.loads(target_row["payload_json"])
    
    if "amount_inr" in payload:
        payload["amount_inr"] = 999999.0
    elif "link_data" in payload and "amount" in payload["link_data"]:
        payload["link_data"]["amount"] = 999999.0
    else:
        payload["hacked"] = True
        
    new_payload_json = json.dumps(payload, sort_keys=True)
    
    cursor.execute('''
        UPDATE recovery_audit_log 
        SET payload_json = ? 
        WHERE id = ?
    ''', (new_payload_json, target_row["id"]))
    
    conn.commit()
    conn.close()
    
    return {"status": "SUCCESS", "hacked_event_id": target_row["event_id"]}

@app.post("/api/reset_demo")
def reset_demo_endpoint():
    seed_demo_data(force=True)
    return {"status": "SUCCESS", "message": "Database reset to 78.5% recovery benchmark with 55 initial blocks."}

@app.post("/api/rollback")
def rollback_chain():
    # Verify ledger to find the broken block ID
    ledger_status = verify_ledger()
    if ledger_status["is_valid"]:
        return {"status": "SKIPPED", "message": "Chain is valid. Nothing to rollback."}
        
    broken_event_id = ledger_status["broken_at_event_id"]
    if not broken_event_id:
        return {"status": "SKIPPED", "message": "Could not identify broken block."}
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get the internal database ID of the broken event
    cursor.execute('SELECT id FROM recovery_audit_log WHERE event_id = ?', (broken_event_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "ERROR", "message": "Broken block not found in DB."}
        
    broken_id = row["id"]
    
    # Delete the broken block and all subsequent blocks
    cursor.execute('DELETE FROM recovery_audit_log WHERE id >= ?', (broken_id,))
    deleted_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return {"status": "SUCCESS", "deleted_blocks": deleted_count, "rolled_back_from": broken_event_id}

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
    
    gmv_silent = 0.0
    gmv_dynamic = 0.0
    gmv_mandate = 0.0
    gmv_b2b = 0.0
    gmv_high_value = 0.0
    
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
            gmv_b2b += amount
        elif is_high_value:
            high_value_holds += 1
            gmv_high_value += amount
        elif action == 'SILENT_RETRY_QUEUED' or cohort == 'TECHNICAL_DOWNTIME':
            silent_retries += 1
            gmv_silent += amount
        elif cohort == 'MANDATE_DEGRADATION' or action == 'UPI_AUTOPAY_MIGRATED':
            mandate_migrations += 1
            gmv_mandate += amount
        elif action == 'DYNAMIC_LINK_SENT' or cohort == 'CONSUMER_CHECKOUT_DROP':
            dynamic_links += 1
            gmv_dynamic += amount
                
        # Realized GMV calculation - sum RESOLVED_RECOVERED full amounts + PENDING_REVIEW_PARTIAL_COMMITMENT milestone amounts
        resolution_status = payload_dict.get("resolution_status")
        if resolution_status:
            if resolution_status == "RESOLVED_RECOVERED":
                total_gmv_recovered += payload_dict.get("milestone_recovered", amount)
            elif resolution_status == "PENDING_REVIEW_PARTIAL_COMMITMENT":
                total_gmv_recovered += payload_dict.get("milestone_recovered", round(amount * 0.30, 2))
        else:
            # Fallback for legacy payloads
            recovered_actions = {
                "DYNAMIC_LINK_SENT",
                "UPI_AUTOPAY_MIGRATION_LINK_CREATED",
                "B2B_DISCOUNT_LINK_CREATED",
                "MANDATE_MIGRATION_INITIATED",
                "INCENTIVE_APPLIED",
                "SUCCESS",
                "CREATED"
            }
            if action in recovered_actions:
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

    gmv_by_rail = {
        "silent_retries": round(gmv_silent, 2),
        "dynamic_links": round(gmv_dynamic, 2),
        "mandate_migrations": round(gmv_mandate, 2),
        "b2b_overdue": round(gmv_b2b, 2),
        "high_value_holds": round(gmv_high_value, 2)
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
        "total_gmv_at_risk": total_gmv_at_risk,
        "total_gmv_recovered": total_gmv_recovered,
        "recovery_rate_pct": round(recovery_rate_pct, 2),
        "total_events_processed": total_events_processed,
        "rail_breakdown": rail_breakdown,
        "gmv_by_rail": gmv_by_rail,
        "ledger_status": ledger_status,
        "active_guardrails_count": active_guardrails_count,
        "latest_guardrails": latest_guardrails,
        "recent_events": recent_events
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Resilix AI"}
