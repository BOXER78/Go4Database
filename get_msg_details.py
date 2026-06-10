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
        
        res, data = mail.fetch(b"25", "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        print(f"From: {msg.get('From')}")
        print(f"Subject: {msg.get('Subject')}")
        print(f"Date: {msg.get('Date')}")
        
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            
        print(f"\nBody:\n{body}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test()
