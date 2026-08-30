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
        return {"is_valid": True, "total_records": 0, "broken_at_id": None}
        
    count = 0
    expected_prev_hash = "0" * 64
    
    for row in rows:
        count += 1
        row_id = row['id']
        event_id = row['event_id']
        timestamp = row['timestamp']
        cohort = row['failure_cohort']
        action = row['action_taken']
        payload_str = row['payload_json']
        prev_hash = row['prev_hash']
        current_hash = row['current_hash']
        
        # 1. Check if prev_hash matches the expected
        if prev_hash != expected_prev_hash:
            return {"is_valid": False, "total_records": count, "broken_at_id": row_id}
            
        # 2. Recompute and check current_hash
        hash_input = f"{prev_hash}|{timestamp}|{event_id}|{cohort}|{action}|{payload_str}"
        recomputed_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        
        if recomputed_hash != current_hash:
            return {"is_valid": False, "total_records": count, "broken_at_id": row_id}
            
        expected_prev_hash = current_hash
        
    return {"is_valid": True, "total_records": count, "broken_at_id": None}
