import time
import requests
import sys

URL = "http://127.0.0.1:8000/api/simulate"

def create_events():
    events = []
    
    # 15x Rail A (Technical Downtime)
    for i in range(15):
        events.append({
            "event_id": f"batch_A_{i:02d}",
            "error_code": "503",
            "error_description": "Bank Internal Error",
            "amount_inr": 1500.0 + i * 10,
            "customer_phone": f"99999990{i:02d}"
        })
        
    # 15x Rail B (Consumer Drop-offs)
    for i in range(15):
        events.append({
            "event_id": f"batch_B_{i:02d}",
            "error_code": "ABORTED",
            "error_description": "User closed window",
            "amount_inr": 800.0 + i * 5,
            "customer_phone": f"88888880{i:02d}"
        })
        
    # 10x Rail C (Mandate Degradations)
    for i in range(10):
        events.append({
            "event_id": f"batch_C_{i:02d}",
            "error_code": "MANDATE_DEGRADED",
            "error_description": "Insufficient Funds",
            "amount_inr": 499.0 + i,
            "customer_phone": f"77777770{i:02d}"
        })
        
    # 10x Rail D (B2B Receivables)
    for i in range(10):
        events.append({
            "event_id": f"batch_D_{i:02d}",
            "error_code": "INVOICE_OVERDUE",
            "error_description": "Net-30 Overdue",
            "amount_inr": 15000.0 + i * 1000,
            "customer_phone": f"66666660{i:02d}"
        })
        
    return events

def run_simulation():
    events = create_events()
    total_events = len(events)
    print(f"\nStarting simulation of {total_events} events...")
    print("=" * 85)
    
    total_gmv = 0.0
    
    for idx, payload in enumerate(events, 1):
        try:
            res = requests.post(URL, json=payload)
            if res.status_code == 200:
                data = res.json()
                cohort = data.get("cohort", "UNKNOWN")
                total_gmv += payload["amount_inr"]
                
                # ASCII visual output
                sys.stdout.write(f"\r[Block {idx:02d}/{total_events:02d}] | Event: {payload['event_id']:<12} | Cohort: {cohort:<23} | GMV Stream: ₹{total_gmv:,.2f}")
                sys.stdout.flush()
            else:
                print(f"\nFailed to process event {payload['event_id']}: {res.status_code}")
        except Exception as e:
            print(f"\nConnection error on event {payload['event_id']}. Is the server running? ({e})")
            return
            
        time.sleep(0.08)
        
    print("\n" + "=" * 85)
    print("Simulation Complete! Check http://127.0.0.1:8000/dashboard to view the ledger.\n")

if __name__ == "__main__":
    run_simulation()
