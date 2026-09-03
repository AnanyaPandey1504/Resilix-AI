import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from app.config import settings

def get_db_connection():
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recovery_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            failure_cohort TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            current_hash TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the table when module is imported
init_db()

def seed_demo_data(force: bool = False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as c FROM recovery_audit_log')
    count = cursor.fetchone()['c']
    
    # Check if DB has only deferred/unseeded rows
    cursor.execute("SELECT COUNT(*) as c FROM recovery_audit_log WHERE action_taken IN ('DYNAMIC_LINK_SENT', 'UPI_AUTOPAY_MIGRATION_LINK_CREATED', 'B2B_DISCOUNT_LINK_CREATED')")
    recovered_count = cursor.fetchone()['c']
    conn.close()
    
    if force or count == 0 or recovered_count == 0:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM recovery_audit_log')
        conn.commit()
        conn.close()
        
        # Prepare 55 records in round-robin interleaved sequence (A -> B -> C -> D -> HV)
        all_seed_records = []
        
        # 15x Rail A (Silent Retry)
        for i in range(15):
            amt = 12500.0 + i * 100
            res_st = "RESOLVED_RECOVERED" if i < 13 else "EXHAUSTED_TIMEOUT"
            ms_rec = amt if res_st == "RESOLVED_RECOVERED" else 0.0
            all_seed_records.append((
                f"demo_A_{i:02d}", "TECHNICAL_DOWNTIME", "SILENT_RETRY_QUEUED",
                {
                    "status": "SILENT_RETRY_QUEUED", "resolution_status": res_st,
                    "amount_inr": amt, "milestone_recovered": ms_rec,
                    "reason": "Bank server down, queuing for silent background retry.",
                    "customer_phone": f"99999990{i:02d}"
                }
            ))
            
        # 15x Rail B (Dynamic Link)
        for i in range(15):
            amt = 18000.0 + i * 200
            res_st = "RESOLVED_RECOVERED" if i < 13 else "ABANDONED_EXPIRED"
            ms_rec = amt if res_st == "RESOLVED_RECOVERED" else 0.0
            all_seed_records.append((
                f"demo_B_{i:02d}", "CONSUMER_CHECKOUT_DROP", "DYNAMIC_LINK_SENT",
                {
                    "status": "DYNAMIC_LINK_SENT", "resolution_status": res_st,
                    "amount_inr": amt, "milestone_recovered": ms_rec,
                    "customer_phone": f"88888880{i:02d}",
                    "link_data": {"status": "created", "payment_link_id": f"plink_b_{i}", "short_url": f"https://rzp.io/i/demo_b_{i}", "amount": amt},
                    "copy": "Aapka payment incomplete reh gaya tha. Is link se payment complete kar lijiye."
                }
            ))
            
        # 10x Rail C (Mandate Degradation)
        for i in range(10):
            amt = 14500.0 + i * 150
            res_st = "RESOLVED_RECOVERED" if i < 9 else "ABANDONED_EXPIRED"
            ms_rec = amt if res_st == "RESOLVED_RECOVERED" else 0.0
            all_seed_records.append((
                f"demo_C_{i:02d}", "MANDATE_DEGRADATION", "UPI_AUTOPAY_MIGRATION_LINK_CREATED",
                {
                    "status": "UPI_AUTOPAY_MIGRATION_LINK_CREATED", "resolution_status": res_st,
                    "amount_inr": amt, "milestone_recovered": ms_rec,
                    "customer_phone": f"77777770{i:02d}",
                    "link_data": {"status": "created", "subscription_id": f"sub_c_{i}", "short_url": f"https://rzp.io/i/demo_c_{i}"}
                }
            ))

        # 10x Rail D (B2B Receivables)
        for i in range(10):
            orig_amt = 35000.0 + i * 1000
            disc_amt = round(orig_amt * 0.98, 2)
            res_st = "RESOLVED_RECOVERED" if i < 9 else "ABANDONED_EXPIRED"
            ms_rec = disc_amt if res_st == "RESOLVED_RECOVERED" else 0.0
            all_seed_records.append((
                f"demo_D_{i:02d}", "B2B_RECEIVABLE_OVERDUE", "B2B_DISCOUNT_LINK_CREATED",
                {
                    "status": "B2B_DISCOUNT_LINK_CREATED", "resolution_status": res_st,
                    "customer_phone": f"66666660{i:02d}",
                    "original_amount": orig_amt, "discounted_amount": disc_amt,
                    "amount_inr": disc_amt, "milestone_recovered": ms_rec,
                    "link_data": {"status": "created", "payment_link_id": f"plink_d_{i}", "short_url": f"https://rzp.io/i/demo_d_{i}", "amount": disc_amt}
                }
            ))
            
        # 5x High-Value Holds
        for i in range(5):
            amt = 28000.0 + i * 1000
            ms_rec = round(amt * 0.30, 2)
            all_seed_records.append((
                f"demo_HV_{i:02d}", "CONSUMER_CHECKOUT_DROP", "REQUIRES_HUMAN_APPROVAL",
                {
                    "status": "BLOCKED_BY_GUARDIAN", "resolution_status": "PENDING_REVIEW_PARTIAL_COMMITMENT",
                    "amount_inr": amt, "milestone_recovered": ms_rec,
                    "reason": "REQUIRES_HUMAN_MANAGER_APPROVAL", "action": "REQUIRES_HUMAN_APPROVAL",
                    "guardrails": {"HIGH_VALUE_GATE": "TRIGGERED - BLOCKED"}
                }
            ))

        # Interleave records (Round Robin across A, B, C, D, HV)
        # Groups: A (15), B (15), C (10), D (10), HV (5)
        a_recs = all_seed_records[0:15]
        b_recs = all_seed_records[15:30]
        c_recs = all_seed_records[30:40]
        d_recs = all_seed_records[40:50]
        hv_recs = all_seed_records[50:55]
        
        interleaved = []
        for i in range(15):
            if i < len(a_recs): interleaved.append(a_recs[i])
            if i < len(b_recs): interleaved.append(b_recs[i])
            if i < len(c_recs): interleaved.append(c_recs[i])
            if i < len(d_recs): interleaved.append(d_recs[i])
            if i < len(hv_recs): interleaved.append(hv_recs[i])
            
        for evt_id, cohort, action, payload in interleaved:
            append_audit_record(evt_id, cohort, action, payload)

def append_audit_record(event_id: str, cohort: str, action: str, payload: dict) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query the latest record's current_hash
    cursor.execute('SELECT current_hash FROM recovery_audit_log ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    
    if row:
        prev_hash = row['current_hash']
    else:
        prev_hash = "0" * 64
        
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_str = json.dumps(payload, sort_keys=True)
    
    hash_input = f"{prev_hash}|{timestamp}|{event_id}|{cohort}|{action}|{payload_str}"
    current_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    cursor.execute('''
        INSERT INTO recovery_audit_log 
        (event_id, timestamp, failure_cohort, action_taken, payload_json, prev_hash, current_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (event_id, timestamp, cohort, action, payload_str, prev_hash, current_hash))
    
    conn.commit()
    conn.close()
    
    return current_hash

def verify_ledger() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM recovery_audit_log ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {"is_valid": True, "total_records": 0, "broken_at_event_id": None}
        
    count = 0
    expected_prev_hash = "0" * 64
    
    for row in rows:
        count += 1
        event_id = row['event_id']
        timestamp = row['timestamp']
        cohort = row['failure_cohort']
        action = row['action_taken']
        payload_str = row['payload_json']
        prev_hash = row['prev_hash']
        current_hash = row['current_hash']
        
        # 1. Check if prev_hash matches the expected
        if prev_hash != expected_prev_hash:
            return {"is_valid": False, "total_records": count, "broken_at_event_id": event_id}
            
        # 2. Recompute and check current_hash
        hash_input = f"{prev_hash}|{timestamp}|{event_id}|{cohort}|{action}|{payload_str}"
        recomputed_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        
        if recomputed_hash != current_hash:
            return {"is_valid": False, "total_records": count, "broken_at_event_id": event_id}
            
        expected_prev_hash = current_hash
        
    return {"is_valid": True, "total_records": count, "broken_at_event_id": None}
