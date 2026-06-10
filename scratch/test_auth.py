import requests
import sys

BASE_URL = "http://127.0.0.1:8080"

def run_tests():
    print("Running authentication & RBAC integration tests...")
    
    # 1. Login with default admin credentials
    payload = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
    if response.status_code != 200:
        print(f"FAILED: Admin login failed with status {response.status_code}")
        sys.exit(1)
    
    data = response.json()
    admin_token = data["token"]
    print(f"SUCCESS: Admin logged in, token: {admin_token}")
    
    # 2. Verify /api/auth/me for admin
    headers = {"X-Session-Token": admin_token}
    me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    if me_resp.status_code != 200 or me_resp.json()["role"] != "Admin":
        print("FAILED: /api/auth/me failed for admin")
        sys.exit(1)
    print("SUCCESS: /api/auth/me verified for admin")
    
    # 3. Create a new Sales Rep user via admin
    user_payload = {
        "name": "Sales Rep 1",
        "email": "sales1@example.com",
        "password": "password123",
        "role": "Sales Rep"
    }
    # Delete first if it already exists to prevent duplicate email errors
    users_resp = requests.get(f"{BASE_URL}/api/users", headers=headers)
    if users_resp.status_code == 200:
        existing_users = users_resp.json()
        sales_user = next((u for u in existing_users if u.get("email") == "sales1@example.com"), None)
        if sales_user:
            del_resp = requests.post(f"{BASE_URL}/api/users/delete/{sales_user['id']}", headers=headers)
            print(f"Cleaned up existing sales1 user: {del_resp.status_code}")
            
    add_resp = requests.post(f"{BASE_URL}/api/users/add", json=user_payload, headers=headers)
    if add_resp.status_code != 200:
        print(f"FAILED: Add team member failed with status {add_resp.status_code}")
        sys.exit(1)
    
    sales_user_id = add_resp.json()["user"]["id"]
    print(f"SUCCESS: Created Sales Rep user with ID {sales_user_id}")
    
    # 4. Login as Sales Rep
    sales_login_payload = {
        "email": "sales1@example.com",
        "password": "password123"
    }
    s_login_resp = requests.post(f"{BASE_URL}/api/auth/login", json=sales_login_payload)
    if s_login_resp.status_code != 200:
        print("FAILED: Sales Rep login failed")
        sys.exit(1)
    
    sales_token = s_login_resp.json()["token"]
    sales_headers = {"X-Session-Token": sales_token}
    print(f"SUCCESS: Sales Rep logged in, token: {sales_token}")
    
    # 5. Verify /api/auth/me for Sales Rep
    s_me_resp = requests.get(f"{BASE_URL}/api/auth/me", headers=sales_headers)
    if s_me_resp.status_code != 200 or s_me_resp.json()["role"] != "Sales Rep":
        print("FAILED: /api/auth/me failed for Sales Rep")
        sys.exit(1)
    print("SUCCESS: /api/auth/me verified for Sales Rep")
    
    # 6. Verify Sales Rep CANNOT access settings (expects 403 Forbidden)
    settings_resp = requests.get(f"{BASE_URL}/api/settings", headers=sales_headers)
    if settings_resp.status_code != 403:
        print(f"FAILED: Sales Rep accessed settings with status {settings_resp.status_code} (expected 403)")
        sys.exit(1)
    print("SUCCESS: Sales Rep restricted from settings (403)")
    
    # 7. Verify Sales Rep CAN fetch leads (expects 200 OK and only filtered hot leads)
    leads_resp = requests.get(f"{BASE_URL}/api/leads", headers=sales_headers)
    if leads_resp.status_code != 200:
        print(f"FAILED: Sales Rep failed to fetch leads with status {leads_resp.status_code}")
        sys.exit(1)
    
    leads = leads_resp.json()
    print(f"SUCCESS: Sales Rep fetched {len(leads)} leads")
    
    # Verify that only hot leads are returned
    hot_statuses = {"Interested", "Replied", "Not_Interested", "OOO", "Wrong_Contact"}
    for lead in leads:
        if lead.get("status") not in hot_statuses:
            print(f"FAILED: Received non-hot lead status {lead.get('status')} for Sales Rep")
            sys.exit(1)
    print("SUCCESS: Verification of hot lead filter for Sales Rep passed")
    
    # 8. Assign a lead to the Sales Rep (using admin session)
    if leads:
        lead_id = leads[0]["id"]
        assign_payload = {"assigned_to": sales_user_id}
        assign_resp = requests.post(f"{BASE_URL}/api/leads/assign/{lead_id}", json=assign_payload, headers=headers)
        if assign_resp.status_code != 200:
            print(f"FAILED: Lead assignment failed with status {assign_resp.status_code}")
            sys.exit(1)
            
        updated_lead = assign_resp.json()["lead"]
        if updated_lead.get("assigned_to") != sales_user_id:
            print("FAILED: Lead assigned_to field not updated properly")
            sys.exit(1)
        print(f"SUCCESS: Assigned lead {lead_id} to sales user {sales_user_id}")
    else:
        print("WARNING: No hot leads available to test assignment. Skipping assignment check.")
        
    print("\nALL AUTHENTICATION AND RBAC TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
