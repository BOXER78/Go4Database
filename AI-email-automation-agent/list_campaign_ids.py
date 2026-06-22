import json

def test():
    with open("campaign_state.json") as f:
        state = json.load(f)
    print(f"Active Campaign ID: {state.get('active_campaign_id')}")
    for cid, camp in state.get("campaigns", {}).items():
        print(f"ID: {cid}, Name: {camp.get('name')}")

if __name__ == "__main__":
    test()
