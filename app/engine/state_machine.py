from datetime import datetime
from typing import Optional

from app.engine.guardians import check_stopping_rules, check_high_value_gate, check_trai_quiet_hours, check_rbi_mandate_notice
from app.agent.triage import diagnose_failure
from app.engine.failure_resilience import resilient_create_payment_link
from app.engine.mandate_rescue import handle_mandate_rescue
from app.engine.receivables_chaser import handle_b2b_receivable
from app.db.crypto_ledger import append_audit_record

def process_recovery_event(
    event_id: str, 
    error_code: str, 
    error_description: str, 
    amount_inr: float, 
    customer_phone: str, 
    touch_count: int = 0, 
    user_opted_out: bool = False, 
    pre_debit_sent_at: Optional[datetime] = None, 
    promised_date_iso: Optional[str] = None, 
    check_dt_ist: Optional[datetime] = None
) -> dict:
    
    guardrail_status = {
        "TRAI_QUIET_HOURS": "SKIPPED - NOT APPLICABLE",
        "HIGH_VALUE_GATE": "SKIPPED - NOT APPLICABLE",
        "RBI_MANDATE": "SKIPPED - NOT APPLICABLE",
        "HARASSMENT_CAP": "SKIPPED - NOT APPLICABLE"
    }

    # Step 1: Telemetry Triage (Determining Cohort first)
    diagnosis = diagnose_failure(error_code, error_description)
    cohort = diagnosis.cohort
    if error_code == "INVOICE_OVERDUE":
        cohort = "B2B_RECEIVABLE_OVERDUE"
        
    # Evaluate Harassment Cap (Applicable to all except TECHNICAL_DOWNTIME since it's silent)
    if cohort != "TECHNICAL_DOWNTIME":
        guardrail_status["HARASSMENT_CAP"] = "EVALUATING"
        is_allowed, stop_reason = check_stopping_rules(touch_count, user_opted_out)
        if not is_allowed:
            guardrail_status["HARASSMENT_CAP"] = "TRIGGERED - BLOCKED"
            payload = {"status": "BLOCKED_BY_GUARDIAN", "reason": stop_reason, "action": "HALT_RECOVERY", "guardrails": guardrail_status}
            audit_hash = append_audit_record(event_id, cohort, "HALT_RECOVERY", payload)
            return _build_response(event_id, cohort, "HALT_RECOVERY", amount_inr, audit_hash, payload)
        guardrail_status["HARASSMENT_CAP"] = "ENFORCING"
        
    # Evaluate High Value Gate (Applicable to all except TECHNICAL_DOWNTIME)
    if cohort != "TECHNICAL_DOWNTIME":
        guardrail_status["HIGH_VALUE_GATE"] = "EVALUATING"
        is_allowed, hv_reason = check_high_value_gate(amount_inr)
        if not is_allowed:
            guardrail_status["HIGH_VALUE_GATE"] = "TRIGGERED - BLOCKED"
            action = "REQUIRES_HUMAN_APPROVAL"
            payload = {"status": "BLOCKED_BY_GUARDIAN", "reason": hv_reason, "action": action, "guardrails": guardrail_status}
            audit_hash = append_audit_record(event_id, cohort, action, payload)
            return _build_response(event_id, cohort, action, amount_inr, audit_hash, payload)
        guardrail_status["HIGH_VALUE_GATE"] = "ENFORCING"
    
    # Step 3: Multi-Rail State Routing
    payload = {}
    action_taken = ""
    
    if cohort == "TECHNICAL_DOWNTIME":
        action_taken = "SILENT_RETRY_QUEUED"
        payload = {
            "status": "SILENT_RETRY_QUEUED",
            "reason": "Bank server down, queuing for silent background retry.",
            "customer_phone": customer_phone
        }
        
    elif cohort == "CONSUMER_CHECKOUT_DROP":
        guardrail_status["TRAI_QUIET_HOURS"] = "EVALUATING"
        is_daytime, trai_reason = check_trai_quiet_hours(check_dt_ist)
        if not is_daytime:
            guardrail_status["TRAI_QUIET_HOURS"] = "TRIGGERED - BLOCKED"
            action_taken = "DEFERRED_TRAI_QUIET_HOURS"
            payload = {
                "status": "DEFERRED_TRAI_QUIET_HOURS",
                "reason": trai_reason,
                "action": "HALT_RECOVERY"
            }
        else:
            guardrail_status["TRAI_QUIET_HOURS"] = "ENFORCING"
            link_res = resilient_create_payment_link(
                amount_inr=amount_inr,
                customer_phone=customer_phone,
                reference_id=f"rec_{event_id}"
            )
            if link_res.get("status") == "DEFERRED_UPSTREAM_LATENCY":
                action_taken = "DEFERRED_UPSTREAM_LATENCY"
                payload = link_res
            else:
                action_taken = "DYNAMIC_LINK_SENT"
                payload = {
                    "status": "DYNAMIC_LINK_SENT",
                    "customer_phone": customer_phone,
                    "link_data": link_res,
                    "copy": diagnosis.localized_hinglish_copy
                }
                
    elif cohort == "MANDATE_DEGRADATION":
        guardrail_status["RBI_MANDATE"] = "EVALUATING"
        is_allowed, reason = check_rbi_mandate_notice(pre_debit_sent_at)
        if not is_allowed:
            guardrail_status["RBI_MANDATE"] = "TRIGGERED - BLOCKED"
            action_taken = "BLOCKED_BY_GUARDIAN"
            payload = {
                "status": "BLOCKED_BY_GUARDIAN",
                "reason": reason,
                "action": "HALT_RECOVERY"
            }
        else:
            guardrail_status["RBI_MANDATE"] = "ENFORCING"
            res = handle_mandate_rescue(event_id, customer_phone, "plan_default", pre_debit_sent_at)
            action_taken = res.get("status", "UNKNOWN")
            payload = res
            
    elif cohort == "B2B_RECEIVABLE_OVERDUE":
        res = handle_b2b_receivable(event_id, amount_inr, customer_phone, promised_date_iso)
        action_taken = res.get("status", "UNKNOWN")
        payload = res

    # Inject guardrail status into final payload
    payload["guardrails"] = guardrail_status

    # Step 4: Record every state outcome
    audit_hash = append_audit_record(event_id, cohort, action_taken, payload)
    
    return _build_response(event_id, cohort, action_taken, amount_inr, audit_hash, payload)

def _build_response(event_id, cohort, action_taken, amount_inr, audit_hash, payload):
    return {
        "event_id": event_id,
        "status": payload.get("status", "UNKNOWN"),
        "cohort": cohort,
        "action_taken": action_taken,
        "amount_inr": amount_inr,
        "ledger_hash": audit_hash,
        "details": payload
    }
