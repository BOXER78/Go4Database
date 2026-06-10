import json

def test():
    with open("campaign_state.json") as f:
        state = json.load(f)
    active_id = state.get("active_campaign_id")
    print(f"Active Campaign ID: {active_id}")
    campaign = state["campaigns"][active_id]
    print("\nLogs:")
    for log in campaign.get("logs", []):
        print(f"[{log.get('level')}] {log.get('timestamp')}: {log.get('message')}")
    print("\nLeads:")
    for lead in campaign.get("leads", []):
        print(f"Name: {lead.get('name')}, Email: {lead.get('email')}, Status: {lead.get('status')}")
        if lead.get("replies"):
            print(f"  Replies: {lead.get('replies')}")

if __name__ == "__main__":
    test()
