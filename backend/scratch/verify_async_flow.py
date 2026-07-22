import sys
import os
import time
import requests

def verify():
    base_url = "http://localhost:8000/api/v1"
    
    # TVSSCS company ID
    company_id = "4c5cfa2f-da31-492e-bf79-9eda94d3db57"
    fiscal_year = 2026
    
    print("Step 1: Enqueuing investment analysis task...")
    payload = {
        "company_id": company_id,
        "fiscal_year": fiscal_year
    }
    
    start_time = time.perf_counter()
    res = requests.post(f"{base_url}/investment/analyze", json=payload)
    if res.status_code != 202:
        print(f"FAILED to enqueue task: HTTP {res.status_code}: {res.text}")
        return
        
    data = res.json()
    task_id = data["task_id"]
    status = data["status"]
    print(f"SUCCESS: Task enqueued! Task ID: {task_id}, Status: {status}")
    
    print("\nStep 2: Polling task status endpoint...")
    while True:
        poll_res = requests.get(f"{base_url}/investment/tasks/{task_id}")
        if poll_res.status_code != 200:
            print(f"FAILED to poll task: HTTP {poll_res.status_code}: {poll_res.text}")
            return
            
        task_data = poll_res.json()
        status = task_data["status"]
        message = task_data.get("message")
        elapsed = time.perf_counter() - start_time
        
        print(f"[{elapsed:.1f}s] Status: {status} | Progress Message: {message}")
        
        if status == "SUCCESS":
            result = task_data["result"]
            print(f"\nSUCCESS: Task completed in {elapsed:.2f} seconds!")
            print(f"Company: {result.get('company_name')}")
            print(f"Intrinsic Value: {result.get('intrinsic_value')}")
            print(f"Report Length: {len(result.get('research_report', ''))} chars")
            break
        elif status == "FAILURE":
            print(f"\nFAILURE: Task failed in {elapsed:.2f} seconds! Error: {task_data.get('error')}")
            break
            
        time.sleep(2)

if __name__ == "__main__":
    verify()
