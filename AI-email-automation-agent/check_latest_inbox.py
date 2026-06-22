import imaplib
import email
import json

def test():
    try:
        with open("campaign_state.json") as f:
            state = json.load(f)
        settings = state.get("settings", {})
        smtp_user = settings.get("smtp_user")
        smtp_password = settings.get("smtp_password")
        
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(smtp_user, smtp_password)
        mail.select("INBOX")
        
        status, messages = mail.search(None, "ALL")
        all_ids = messages[0].split()
        print(f"Total messages in INBOX: {len(all_ids)}")
        for msg_id in all_ids[-3:]:
            res, msg_data = mail.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    print(f"ID: {msg_id.decode()}, Date: {msg.get('Date')}, From: {msg.get('From')}, Subject: {msg.get('Subject')}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test()
