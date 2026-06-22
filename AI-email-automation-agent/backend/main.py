import os
import sys
# Inject backend directory into search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import datetime
import threading
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import pandas as pd
import io
from typing import List, Dict, Any, Optional
import socket

# Set default socket timeout to 10 seconds to prevent IMAP/SMTP hanging
socket.setdefaulttimeout(10)

from enum import Enum
from lead_manager import LeadManager
from agent_logic import analyze_and_draft, classify_reply, generate_custom_followup, qualify_and_draft_reply

class ConversationStage(Enum):
    COLD_OUTREACH = "COLD_OUTREACH"
    MQL = "MQL"
    SQL_SAMPLE_APPROVAL = "SQL_SAMPLE_APPROVAL"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    DEAL_CLOSURE = "DEAL_CLOSURE"

app = FastAPI(title="Go4Database AI Sales Outreach Agent")
lead_manager = LeadManager()

# Global session management tracking (token -> user dict)
# Prepopulate bypass_token for local/automatic tests integration
active_sessions = {
    "bypass_token": {
        "id": "admin_user",
        "name": "Admin User",
        "email": "admin@admin.com",
        "role": "Admin"
    }
}

def get_current_user(x_session_token: Optional[str] = Header(None), token: Optional[str] = None):
    tok = x_session_token or token
    if not tok or tok not in active_sessions:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return active_sessions[tok]

def verify_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin access required")
    return user

# Global worker variables
worker_thread = None
worker_running = False

# Ensure static directory exists
os.makedirs("static", exist_ok=True)

# Helper: SMTP Sender
def send_email_via_smtp(settings: dict, to_email: str, subject: str, body: str) -> bool:
    """
    Attempts to send a real email using configured SMTP settings.
    If credentials are empty, returns False (which triggers Mock simulation).
    """
    if not settings.get("smtp_user") or not settings.get("smtp_password"):
        return False # Fallback to mock

    try:
        msg = MIMEMultipart()
        msg['From'] = f"{settings.get('sender_name')} <{settings.get('sender_email') or settings.get('smtp_user')}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(settings.get("smtp_server", "smtp.gmail.com"), settings.get("smtp_port", 587))
        server.starttls()
        server.login(settings.get("smtp_user"), settings.get("smtp_password"))
        server.sendmail(msg['From'], to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"SMTP sending failed: {e}")
        raise e

def get_imap_server_from_smtp(smtp_server: str) -> str:
    smtp_lower = smtp_server.lower()
    if "gmail.com" in smtp_lower:
        return "imap.gmail.com"
    elif "yahoo.com" in smtp_lower:
        return "imap.mail.yahoo.com"
    elif "office365.com" in smtp_lower or "outlook.com" in smtp_lower:
        return "outlook.office365.com"
    if smtp_lower.startswith("smtp."):
        return "imap." + smtp_server[5:]
    return smtp_server

def get_all_enabled_sender_accounts(settings: dict) -> list:
    accounts = []
    
    # 1. Add primary account if configured
    primary_user = settings.get("smtp_user")
    primary_pass = settings.get("smtp_password") or ""
    if primary_user:
        accounts.append({
            "id": "primary",
            "name": settings.get("sender_name") or "Primary Sender",
            "email": settings.get("sender_email") or primary_user,
            "sender_name": settings.get("sender_name") or "Primary Sender",
            "sender_email": settings.get("sender_email") or primary_user,
            "smtp_user": primary_user,
            "smtp_password": primary_pass,
            "smtp_server": settings.get("smtp_server") or "smtp.gmail.com",
            "smtp_port": int(settings.get("smtp_port") or 587),
            "imap_server": settings.get("imap_server") or get_imap_server_from_smtp(settings.get("smtp_server") or "smtp.gmail.com"),
            "imap_port": int(settings.get("imap_port") or 993),
            "is_active": True
        })
        
    # 2. Add active additional accounts
    additional_accounts = settings.get("sender_accounts", [])
    for acc in additional_accounts:
        if acc.get("is_active", True) and acc.get("smtp_user"):
            accounts.append({
                "id": acc.get("id") or acc.get("smtp_user"),
                "name": acc.get("name") or settings.get("sender_name") or "Rotation Sender",
                "email": acc.get("email") or acc.get("smtp_user"),
                "sender_name": acc.get("name") or settings.get("sender_name") or "Rotation Sender",
                "sender_email": acc.get("email") or acc.get("smtp_user"),
                "smtp_user": acc.get("smtp_user"),
                "smtp_password": acc.get("smtp_password") or "",
                "smtp_server": acc.get("smtp_server") or "smtp.gmail.com",
                "smtp_port": int(acc.get("smtp_port") or 587),
                "imap_server": acc.get("imap_server") or get_imap_server_from_smtp(acc.get("smtp_server") or "smtp.gmail.com"),
                "imap_port": int(acc.get("imap_port") or 993),
                "is_active": True
            })
            
    return accounts

def get_active_sender_accounts(settings: dict) -> list:
    accounts = get_all_enabled_sender_accounts(settings)
    
    # Filter out accounts that have completed warmup (either 14 days or total cap)
    try:
        warmup_progress = calculate_warmup_progress(lead_manager.state)
        filtered_accounts = []
        for acc in accounts:
            email = acc["email"].lower().strip()
            progress = warmup_progress.get(email, {})
            if not progress.get("is_completed", False):
                filtered_accounts.append(acc)
            else:
                print(f"[WARMUP COMPLETE] Excluding {email} from active pool.")
        return filtered_accounts
    except Exception as e:
        print(f"Error filtering warmup completed accounts: {e}")
        return accounts


def get_sender_account_by_id(settings: dict, account_id: str) -> dict:
    primary_user = settings.get("smtp_user")
    primary_pass = settings.get("smtp_password")
    
    # Check primary first
    if account_id == "primary":
        return {
            "id": "primary",
            "name": settings.get("sender_name") or "Primary Sender",
            "email": settings.get("sender_email") or primary_user or "simulated@example.com",
            "sender_name": settings.get("sender_name") or "Primary Sender",
            "sender_email": settings.get("sender_email") or primary_user or "simulated@example.com",
            "smtp_user": primary_user or "",
            "smtp_password": primary_pass or "",
            "smtp_server": settings.get("smtp_server") or "smtp.gmail.com",
            "smtp_port": int(settings.get("smtp_port") or 587),
            "imap_server": settings.get("imap_server") or get_imap_server_from_smtp(settings.get("smtp_server") or "smtp.gmail.com"),
            "imap_port": int(settings.get("imap_port") or 993),
            "is_active": True
        }
        
    # Check additional accounts
    additional_accounts = settings.get("sender_accounts", [])
    for acc in additional_accounts:
        if acc.get("id") == account_id or (not acc.get("id") and acc.get("smtp_user") == account_id):
            return {
                "id": acc.get("id") or acc.get("smtp_user"),
                "name": acc.get("name") or settings.get("sender_name") or "Rotation Sender",
                "email": acc.get("email") or acc.get("smtp_user"),
                "sender_name": acc.get("name") or settings.get("sender_name") or "Rotation Sender",
                "sender_email": acc.get("email") or acc.get("smtp_user"),
                "smtp_user": acc.get("smtp_user"),
                "smtp_password": acc.get("smtp_password"),
                "smtp_server": acc.get("smtp_server") or "smtp.gmail.com",
                "smtp_port": int(acc.get("smtp_port") or 587),
                "imap_server": acc.get("imap_server") or get_imap_server_from_smtp(acc.get("smtp_server") or "smtp.gmail.com"),
                "imap_port": int(acc.get("imap_port") or 993),
                "is_active": acc.get("is_active", True)
            }
            
    # Fallback to primary
    return {
        "id": "primary",
        "name": settings.get("sender_name") or "Primary Sender",
        "email": settings.get("sender_email") or primary_user or "simulated@example.com",
        "sender_name": settings.get("sender_name") or "Primary Sender",
        "sender_email": settings.get("sender_email") or primary_user or "simulated@example.com",
        "smtp_user": primary_user or "",
        "smtp_password": primary_pass or "",
        "smtp_server": settings.get("smtp_server") or "smtp.gmail.com",
        "smtp_port": int(settings.get("smtp_port") or 587),
        "imap_server": settings.get("imap_server") or get_imap_server_from_smtp(settings.get("smtp_server") or "smtp.gmail.com"),
        "imap_port": int(settings.get("imap_port") or 993),
        "is_active": True
    }

def parse_dt_to_utc(dt_str: str):
    try:
        dt = datetime.datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.astimezone(datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt
    except Exception:
        return None

def check_imap_replies(account: dict, all_lead_emails: set) -> list:
    """
    Connects to the IMAP server, checks for new/unread and recent emails,
    and returns a list of dictionaries with sender email, body, subject, message_id,
    and bounce status for any emails that come from our leads.
    """
    import imaplib
    import email
    import email.utils
    import re

    smtp_user = account.get("smtp_user")
    smtp_password = account.get("smtp_password")
    smtp_server = account.get("smtp_server")
    
    if not smtp_user or not smtp_password or not smtp_server:
        return []
        
    imap_server = account.get("imap_server") or get_imap_server_from_smtp(smtp_server)
    imap_port = int(account.get("imap_port") or 993)
    
    replies_found = []
    try:
        mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=10)
        mail.login(smtp_user, smtp_password)
        
        folders_to_check = ["INBOX"]
        try:
            status, folder_list = mail.list()
            if status == "OK":
                for f in folder_list:
                    f_str = f.decode()
                    if "\\junk" in f_str.lower() or "spam" in f_str.lower() or "junk" in f_str.lower():
                        parts = f_str.split(' "/" ')
                        if len(parts) > 1:
                            spam_folder = parts[1].strip('"')
                            if spam_folder not in folders_to_check:
                                folders_to_check.append(spam_folder)
                        else:
                            parts = f_str.split()
                            if parts:
                                spam_folder = parts[-1].strip('"')
                                if spam_folder not in folders_to_check:
                                    folders_to_check.append(spam_folder)
                        break
        except Exception as list_err:
            print(f"Error listing folders for spam check: {list_err}")
            
        mailbox_selected = False
        
        for folder in folders_to_check:
            try:
                select_status, select_data = mail.select(f'"{folder}"')
                if select_status != "OK":
                    continue
                mailbox_selected = True
                
                # 1. Fetch UNSEEN message IDs
                status_unseen, messages_unseen = mail.search(None, "UNSEEN")
                unseen_ids = messages_unseen[0].split() if status_unseen == "OK" and messages_unseen[0] else []
                
                # 2. Fetch ALL message IDs to check the last 50
                status_all, messages_all = mail.search(None, "ALL")
                all_ids = messages_all[0].split() if status_all == "OK" and messages_all[0] else []
                recent_ids = all_ids[-50:]
                
                # Combine IDs chronologically, removing duplicates
                combined_set = set(unseen_ids + recent_ids)
                mail_ids = sorted(list(combined_set), key=lambda x: int(x))
                
                if not mail_ids:
                    continue
                    
                # Batch fetch headers to speed up check significantly (1 roundtrip instead of len(mail_ids) roundtrips)
                try:
                    mail_ids_bytes = b",".join(mail_ids)
                    res_headers, header_data = mail.fetch(mail_ids_bytes, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
                except Exception as fetch_err:
                    print(f"Error batch fetching headers: {fetch_err}", flush=True)
                    continue
                    
                if res_headers != "OK" or not header_data:
                    continue
                
                for part in header_data:
                    if not isinstance(part, tuple):
                        continue
                        
                    # Extract the mail_id (sequence number) from part[0]
                    try:
                        mail_id = part[0].split()[0]
                    except Exception:
                        continue
                        
                    header_msg = email.message_from_bytes(part[1])
                    
                    msg_id_val = None
                    from_email = None
                    subject_val = ""
                    date_val = None
                    
                    from_header = header_msg.get("From", "")
                    parsed_from = email.utils.parseaddr(from_header)
                    if parsed_from and parsed_from[1]:
                        from_email = parsed_from[1].lower().strip()
                    
                    msg_id_val = header_msg.get("Message-ID")
                    if msg_id_val:
                        msg_id_val = msg_id_val.strip()
                        
                    subject_val = header_msg.get("Subject", "")
                    date_header = header_msg.get("Date")
                    if date_header:
                        try:
                            date_val = email.utils.parsedate_to_datetime(date_header)
                            if date_val.tzinfo is None:
                                date_val = date_val.replace(tzinfo=datetime.timezone.utc)
                            else:
                                date_val = date_val.astimezone(datetime.timezone.utc)
                        except Exception:
                            date_val = None
                    
                    # Check if it is a bounce
                    is_bounce = False
                    if from_email and any(x in from_email for x in ["mailer-daemon", "postmaster", "bounce", "mail-noreply", "noreply"]):
                        is_bounce = True
                    
                    matched_lead_email = None
                    if from_email and from_email in all_lead_emails:
                        matched_lead_email = from_email
                    
                    # If it is not from a lead and not a bounce, we don't need to process it
                    if not matched_lead_email and not is_bounce:
                        continue
                        
                    # Fetch the full email body
                    res, msg_data = mail.fetch(mail_id, "(RFC822)")
                    if res != "OK":
                        continue
                        
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            body = ""
                            if msg.is_multipart():
                                for part_walk in msg.walk():
                                    content_type = part_walk.get_content_type()
                                    content_disposition = str(part_walk.get("Content-Disposition"))
                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        try:
                                            body = part_walk.get_payload(decode=True).decode(part_walk.get_content_charset() or "utf-8", errors="ignore")
                                        except Exception:
                                            pass
                                        break
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
                                except Exception:
                                    pass
                                    
                            if not body:
                                for part_walk in msg.walk():
                                    content_type = part_walk.get_content_type()
                                    if content_type == "text/html":
                                        try:
                                            html_body = part_walk.get_payload(decode=True).decode(part_walk.get_content_charset() or "utf-8", errors="ignore")
                                            body = re.sub('<[^<]+?>', '', html_body)
                                        except Exception:
                                            pass
                                        break
                                        
                            if is_bounce:
                                search_text = (subject_val + " " + body).lower()
                                for le in all_lead_emails:
                                    if le in search_text:
                                        matched_lead_email = le
                                        break
                            
                            if matched_lead_email or is_bounce:
                                mail.store(mail_id, "+FLAGS", "\\Seen")
                                
                                replies_found.append({
                                    "sender": matched_lead_email,
                                    "body": body.strip(),
                                    "subject": subject_val,
                                    "is_bounce": is_bounce,
                                    "message_id": msg_id_val,
                                    "date_val": date_val
                                })
            except Exception as folder_err:
                print(f"Error checking folder {folder} for {smtp_user}: {folder_err}", flush=True)
                
        if mailbox_selected:
            try:
                mail.close()
            except Exception:
                pass
        mail.logout()
    except Exception as e:
        print(f"IMAP check failed for {smtp_user}: {e}", flush=True)
        lead_manager.add_log("ERROR", f"IMAP connection failed for {smtp_user}: {str(e)}")
        
    return replies_found

# Background Worker for Email Campaign Sending and Follow-up Checks
def campaign_worker_loop():
    global worker_running
    lead_manager.add_log("SYSTEM", "Campaign background worker thread started.")
    last_imap_check_time = 0
    
    while worker_running:
        campaigns = lead_manager.get_campaigns()
        settings = lead_manager.get_settings()
        
        # Check IMAP for replies every 30 seconds
        now_ts = time.time()
        if now_ts - last_imap_check_time >= 30:
            print(f"BG worker: starting IMAP check for {len(campaigns)} campaigns...", flush=True)
            all_accounts = get_all_enabled_sender_accounts(settings)
            if all_accounts:
                # 1. Collect all lead emails
                all_lead_emails = set()
                for c in campaigns:
                    leads = lead_manager.get_leads(campaign_id=c["id"])
                    for l in leads:
                        if l.get("email"):
                            all_lead_emails.add(l["email"].lower().strip())
                
                # 2. Poll each account once
                for account in all_accounts:
                    if not account.get("smtp_user") or not account.get("smtp_password"):
                        continue
                    
                    # Skip IMAP polling for Microsoft 365 / Outlook accounts since Basic Auth is disabled by Microsoft
                    smtp_server = (account.get("smtp_server") or "").lower()
                    imap_server = (account.get("imap_server") or "").lower()
                    if "office365" in smtp_server or "outlook" in smtp_server or "office365" in imap_server or "outlook" in imap_server:
                        continue
                    
                    real_replies = check_imap_replies(account, all_lead_emails)
                    if real_replies:
                        print(f"BG worker: found {len(real_replies)} replies/bounces for account {account['email']}", flush=True)
                        
                        # 3. Match replies with campaigns
                        for reply in real_replies:
                            sender = reply["sender"]
                            body = reply["body"]
                            msg_id = reply.get("message_id")
                            is_bounce = reply.get("is_bounce")
                            date_val = reply.get("date_val")
                            subject_val = reply.get("subject")
                            
                            # Find which campaigns have a lead matching this sender or bounce
                            for c in campaigns:
                                campaign_id = c["id"]
                                leads = lead_manager.get_leads(campaign_id=campaign_id)
                                
                                matched_lead = None
                                if is_bounce:
                                    search_text = (subject_val + " " + body).lower()
                                    for lead in leads:
                                        if lead.get("email") and lead["email"].lower().strip() in search_text:
                                            matched_lead = lead
                                            break
                                else:
                                    if sender:
                                        matched_lead = next((l for l in leads if l["email"].lower().strip() == sender), None)
                                        
                                if matched_lead:
                                    # Deduplicate
                                    already_processed = False
                                    with lead_manager.lock:
                                        campaign_obj = lead_manager.state["campaigns"].get(campaign_id)
                                        if campaign_obj:
                                            if "processed_message_ids" not in campaign_obj:
                                                campaign_obj["processed_message_ids"] = []
                                            if msg_id:
                                                if msg_id in campaign_obj["processed_message_ids"]:
                                                    already_processed = True
                                                else:
                                                    campaign_obj["processed_message_ids"].append(msg_id)
                                                    
                                    if already_processed:
                                        continue
                                        
                                    # Verify dates
                                    last_sent_str = matched_lead.get("last_sent_time")
                                    if not last_sent_str:
                                        continue
                                    last_sent_dt = parse_dt_to_utc(last_sent_str)
                                    if last_sent_dt and date_val and date_val <= last_sent_dt:
                                        continue
                                        
                                    if is_bounce:
                                        with lead_manager.lock:
                                            matched_lead["status"] = "Junk"
                                            matched_lead["history"].append({
                                                "timestamp": datetime.datetime.now().isoformat(),
                                                "action": "Email Bounced",
                                                "details": f"Delivery bounce notice: {subject_val}\n\n{body[:250]}... (Account: {account.get('email')})"
                                            })
                                        lead_manager.add_log("ERROR", f"Outbound email to {matched_lead['name']} ({matched_lead['email']}) bounced. Marked as Junk. (Account: {account.get('email')})", matched_lead["id"], campaign_id)
                                        lead_manager.update_campaign_stats_unsafe(campaign_id)
                                        lead_manager.save_state()
                                    else:
                                        print(f"BG worker: processing reply from {matched_lead['name']} in campaign {campaign_id}", flush=True)
                                        handle_received_reply(matched_lead, body, campaign_id, is_simulated=False)
            last_imap_check_time = time.time()

        for c in campaigns:
            if c.get("is_running", False) or c.get("start_date"):
                # Check start_date if configured
                start_date_str = c.get("start_date")
                if start_date_str:
                    try:
                        start_date_dt = datetime.datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                        if start_date_dt.tzinfo is not None:
                            now_compare = datetime.datetime.now(datetime.timezone.utc)
                        else:
                            now_compare = datetime.datetime.now()
                        
                        if now_compare < start_date_dt:
                            # Scheduled for future, skip it
                            continue
                        elif not c.get("is_running", False):
                            # Past start_date, start it!
                            lead_manager.set_campaign_running(True, campaign_id=c["id"])
                            lead_manager.set_campaign_start_date(c["id"], None)
                            c["is_running"] = True
                            lead_manager.add_log("SYSTEM", f"Campaign automatically started based on scheduled start date: {start_date_str}", None, c["id"])
                    except Exception as parse_err:
                        print(f"Error parsing campaign start_date '{start_date_str}': {parse_err}", flush=True)

                if not c.get("is_running", False):
                    continue

                campaign_id = c["id"]
                leads = lead_manager.get_leads(campaign_id=campaign_id)
                now = datetime.datetime.now()
                
                lead_processed = False
                
                for lead in leads:
                    # 0. Auto-analyze if Pending and campaign is running
                    if lead["status"] == "Pending":
                        with lead_manager.lock:
                            lead["status"] = "Analyzing"
                        api_key = settings.get("gemini_api_key", "")
                        threading.Thread(
                            target=run_ai_analysis_background,
                            args=(lead["id"], api_key, campaign_id),
                            daemon=True
                        ).start()
                        lead_processed = True
                        continue
                    
                    # 1. Process Initial Pitch
                    is_eligible_initial = False
                    if lead["status"] == "Ready":
                        if settings.get("automation_mode", False):
                            is_eligible_initial = True
                        elif lead.get("is_approved", False):
                            is_eligible_initial = True
                    
                    if is_eligible_initial:
                        active_accounts = get_active_sender_accounts(settings)
                        has_configured_accounts = bool(settings.get("smtp_user") or settings.get("sender_accounts"))
                        
                        if not active_accounts and has_configured_accounts:
                            lead_manager.add_log("SYSTEM", "All configured sender accounts have completed their warmup. Outreach paused.", None, campaign_id)
                            lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                            break
                            
                        if not active_accounts:
                            # Create a mock/simulated account so simulation mode still runs
                            active_accounts = [{
                                "id": "primary",
                                "name": settings.get("sender_name") or "Primary Sender (Simulated)",
                                "email": settings.get("sender_email") or "simulated@example.com",
                                "sender_name": settings.get("sender_name") or "Primary Sender (Simulated)",
                                "sender_email": settings.get("sender_email") or "simulated@example.com",
                                "smtp_user": "",
                                "smtp_password": "",
                                "smtp_server": "",
                                "smtp_port": 587,
                                "imap_server": "",
                                "imap_port": 993,
                                "is_active": True
                            }]
                        
                        # Check Global Limit
                        global_limit = int(settings.get("daily_limit", 50))
                        sent_today_global = sum(1 for c_temp in campaigns for l in lead_manager.get_leads(campaign_id=c_temp["id"]) 
                                                for h in l.get("history", []) if h.get("action", "").startswith("Email Sent") 
                                                and datetime.datetime.fromisoformat(h.get("timestamp", "2000-01-01")).date() == now.date())
                        if sent_today_global >= global_limit:
                             lead_manager.add_log("SYSTEM", f"Reached global daily email limit of {global_limit}. Pausing campaign.", None, campaign_id)
                             lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                             break

                        # Select rotation account that is not capped
                        selected_account = None
                        default_schedule = {
                            "1": 5, "2": 8, "3": 10, "4": 12, "5": 15, "6": 18, "7": 20,
                            "8": 25, "9": 30, "10": 35, "11": 40, "12": 45, "13": 50, "14": 50
                        }
                        warmup_schedule = settings.get("warmup_schedule", default_schedule)
                        warmup_total_cap = int(settings.get("warmup_total_cap", 50))
                        warmup_progress = calculate_warmup_progress(lead_manager.state)
                        
                        rot_idx = settings.get("rotation_index", 0)
                        if rot_idx >= len(active_accounts):
                            rot_idx = 0
                            
                        for i in range(len(active_accounts)):
                            idx = (rot_idx + i) % len(active_accounts)
                            acc = active_accounts[idx]
                            email = acc.get("email", "").lower().strip()
                            
                            if email == "simulated@example.com":
                                selected_account = acc
                                with lead_manager.lock:
                                    settings["rotation_index"] = (idx + 1) % len(active_accounts)
                                lead_manager.update_settings({"rotation_index": settings["rotation_index"]})
                                break
                                
                            prog = warmup_progress.get(email, {})
                            sent_dates = prog.get("dates", [])
                            today_str = datetime.date.today().isoformat()
                            if today_str in sent_dates:
                                day = len(sent_dates)
                            else:
                                day = len(sent_dates) + 1
                                
                            limit = int(warmup_schedule.get(str(day)) or warmup_schedule.get(day) or 50)
                            sent_today = prog.get("sent_today", 0)
                            total_sent = prog.get("total_sent", 0)
                            
                            if sent_today < limit and total_sent < warmup_total_cap:
                                selected_account = acc
                                with lead_manager.lock:
                                    settings["rotation_index"] = (idx + 1) % len(active_accounts)
                                lead_manager.update_settings({"rotation_index": settings["rotation_index"]})
                                break
                                
                        if not selected_account and has_configured_accounts:
                            lead_manager.add_log("SYSTEM", "All active sender accounts have reached their daily warmup limit today. Outreach paused.", None, campaign_id)
                            lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                            break
                        
                        if not selected_account:
                            # Fallback if no account configured at all (simulation mode)
                            selected_account = active_accounts[0]

                        lead_manager.update_lead_status(
                            lead["id"], "Sending", "Sending Email 1", 
                            f"Preparing to send initial pitch from {selected_account['email']}: '{lead['email_drafts']['initial_pitch']['subject']}'",
                            campaign_id=campaign_id
                        )
                        
                        draft = lead["email_drafts"]["initial_pitch"]
                        subject = draft["subject"]
                        body = draft["body"].replace("[Sender Name]", selected_account.get("sender_name", "Go4Database Agent"))
                        
                        try:
                            sent_real = send_email_via_smtp(selected_account, lead["email"], subject, body)
                            if sent_real:
                                details = f"Email sent successfully via SMTP to {lead['email']} (Sender: {selected_account['email']})"
                            else:
                                details = f"[SIMULATED] Email sent successfully to {lead['email']} (Sender: {selected_account['email']})"
                            
                            new_history = list(lead["history"]) + [{
                                "timestamp": now.isoformat(),
                                "action": "Email Sent (Initial)",
                                "details": details + f"\nSubject: {subject}"
                            }]
                            lead_manager.update_lead_sent_state(
                                lead["id"], "Sent", now.isoformat(), 1, new_history,
                                sender_account_id=selected_account["id"], campaign_id=campaign_id
                            )
                            lead_manager.add_log("INFO", f"Sent initial pitch to {lead['name']} ({lead['company']}) from {selected_account['email']}.", lead["id"], campaign_id)
                            
                        except Exception as e:
                            import smtplib
                            if isinstance(e, smtplib.SMTPRecipientsRefused):
                                lead_manager.update_lead_status(
                                    lead["id"], "Junk", "Bounced (Immediate)", 
                                    f"SMTP server refused recipient address (wrong email): {str(e)}",
                                    campaign_id=campaign_id
                                )
                                lead_manager.add_log("ERROR", f"Failed to send initial email to {lead['name']} ({lead['email']}): Recipient refused. Marked as Junk.", lead["id"], campaign_id)
                            else:
                                lead_manager.update_lead_status(
                                    lead["id"], "Ready", "Send Error", 
                                    f"Failed to send email: {str(e)}",
                                    campaign_id=campaign_id
                                )
                                lead_manager.add_log("ERROR", f"Failed to send email to {lead['name']}: {str(e)}", lead["id"], campaign_id)
                        
                        lead_processed = True
                        delay = int(settings.get("min_delay", 5))
                        time.sleep(delay)
                        break
                    
                    # 2. Process Auto Follow-up 1
                    if lead["status"] == "Sent" and lead.get("sequence_step") == 1:
                        last_sent = datetime.datetime.fromisoformat(lead["last_sent_time"])
                        delay_hours = float(settings.get("followup_delay_1_hours", 48))
                        delay_seconds = int(delay_hours * 3600)
                        
                        if (now - last_sent).total_seconds() >= delay_seconds:
                            sender_account_id = lead.get("sender_account_id", "primary")
                            selected_account = get_sender_account_by_id(settings, sender_account_id)
                            
                            # Check Global Limit
                            global_limit = int(settings.get("daily_limit", 50))
                            sent_today_global = sum(1 for c_temp in campaigns for l in lead_manager.get_leads(campaign_id=c_temp["id"]) 
                                                    for h in l.get("history", []) if h.get("action", "").startswith("Email Sent") 
                                                    and datetime.datetime.fromisoformat(h.get("timestamp", "2000-01-01")).date() == now.date())
                            if sent_today_global >= global_limit:
                                 lead_manager.add_log("SYSTEM", f"Reached global daily email limit of {global_limit}. Pausing campaign.", None, campaign_id)
                                 lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                                 break

                            # Check per-mailbox warmup & cap limits
                            email = selected_account.get("email", "").lower().strip()
                            if email != "simulated@example.com":
                                warmup_progress = calculate_warmup_progress(lead_manager.state)
                                prog = warmup_progress.get(email, {})
                                
                                # Check total cap
                                total_sent = prog.get("total_sent", 0)
                                warmup_total_cap = int(settings.get("warmup_total_cap", 50))
                                if total_sent >= warmup_total_cap:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 1 for {lead['name']}: sender {email} completed warmup (reached total cap of {warmup_total_cap}).", lead["id"], campaign_id)
                                    continue
                                
                                # Check warmup days cap (14 days)
                                sent_dates = prog.get("dates", [])
                                if len(sent_dates) >= 14:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 1 for {lead['name']}: sender {email} completed 14-day warmup.", lead["id"], campaign_id)
                                    continue
                                
                                # Check daily warmup limit
                                today_str = datetime.date.today().isoformat()
                                if today_str in sent_dates:
                                    day = len(sent_dates)
                                else:
                                    day = len(sent_dates) + 1
                                    
                                default_schedule = {
                                    "1": 5, "2": 8, "3": 10, "4": 12, "5": 15, "6": 18, "7": 20,
                                    "8": 25, "9": 30, "10": 35, "11": 40, "12": 45, "13": 50, "14": 50
                                }
                                warmup_schedule = settings.get("warmup_schedule", default_schedule)
                                daily_limit = int(warmup_schedule.get(str(day)) or warmup_schedule.get(day) or 50)
                                sent_today = prog.get("sent_today", 0)
                                
                                if sent_today >= daily_limit:
                                    # Mailbox hit daily limit, skip this follow-up for today
                                    continue

                            lead_manager.update_lead_status(
                                lead["id"], "Sending", "Sending Follow-up 1", 
                                f"Sending automatic follow-up 1 from {selected_account['email']} (no reply detected)",
                                campaign_id=campaign_id
                            )
                            
                            draft = lead["email_drafts"]["follow_up_1"]
                            subject = draft["subject"]
                            body = draft["body"].replace("[Sender Name]", selected_account.get("sender_name", "Go4Database Agent"))
                            
                            try:
                                sent_real = send_email_via_smtp(selected_account, lead["email"], subject, body)
                                if sent_real:
                                    details = f"Follow-up 1 sent via SMTP to {lead['email']} (Sender: {selected_account['email']})"
                                else:
                                    details = f"[SIMULATED] Follow-up 1 sent to {lead['email']} (Sender: {selected_account['email']})"
                                    
                                new_history = list(lead["history"]) + [{
                                    "timestamp": now.isoformat(),
                                    "action": "Email Sent (Follow-up 1)",
                                    "details": details + f"\nSubject: {subject}"
                                }]
                                lead_manager.update_lead_sent_state(
                                    lead["id"], "Follow_Up_1_Sent", now.isoformat(), 2, new_history,
                                    sender_account_id=selected_account["id"], campaign_id=campaign_id
                                )
                                lead_manager.add_log("INFO", f"Sent follow-up 1 to {lead['name']} ({lead['company']}) from {selected_account['email']}.", lead["id"], campaign_id)
                                
                            except Exception as e:
                                import smtplib
                                if isinstance(e, smtplib.SMTPRecipientsRefused):
                                    lead_manager.update_lead_status(
                                        lead["id"], "Junk", "Bounced (Immediate)", 
                                        f"SMTP server refused recipient address (wrong email): {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 1 to {lead['name']} ({lead['email']}): Recipient refused. Marked as Junk.", lead["id"], campaign_id)
                                else:
                                    lead_manager.update_lead_status(
                                        lead["id"], "Sent", "Send Error",
                                        f"Failed to send follow-up 1: {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 1 to {lead['name']}: {str(e)}", lead["id"], campaign_id)
                            
                            lead_processed = True
                            time.sleep(int(settings.get("min_delay", 5)))
                            break
                    
                    # 3. Process Auto Follow-up 2
                    if lead["status"] == "Follow_Up_1_Sent" and lead.get("sequence_step") == 2:
                        last_sent = datetime.datetime.fromisoformat(lead["last_sent_time"])
                        delay_hours = float(settings.get("followup_delay_2_hours", 48))
                        delay_seconds = int(delay_hours * 3600)
                        
                        if (now - last_sent).total_seconds() >= delay_seconds:
                            sender_account_id = lead.get("sender_account_id", "primary")
                            selected_account = get_sender_account_by_id(settings, sender_account_id)
                            
                            # Check Global Limit
                            global_limit = int(settings.get("daily_limit", 50))
                            sent_today_global = sum(1 for c_temp in campaigns for l in lead_manager.get_leads(campaign_id=c_temp["id"]) 
                                                    for h in l.get("history", []) if h.get("action", "").startswith("Email Sent") 
                                                    and datetime.datetime.fromisoformat(h.get("timestamp", "2000-01-01")).date() == now.date())
                            if sent_today_global >= global_limit:
                                 lead_manager.add_log("SYSTEM", f"Reached global daily email limit of {global_limit}. Pausing campaign.", None, campaign_id)
                                 lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                                 break

                            # Check per-mailbox warmup & cap limits
                            email = selected_account.get("email", "").lower().strip()
                            if email != "simulated@example.com":
                                warmup_progress = calculate_warmup_progress(lead_manager.state)
                                prog = warmup_progress.get(email, {})
                                
                                # Check total cap
                                total_sent = prog.get("total_sent", 0)
                                warmup_total_cap = int(settings.get("warmup_total_cap", 50))
                                if total_sent >= warmup_total_cap:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 2 for {lead['name']}: sender {email} completed warmup (reached total cap of {warmup_total_cap}).", lead["id"], campaign_id)
                                    continue
                                
                                # Check warmup days cap (14 days)
                                sent_dates = prog.get("dates", [])
                                if len(sent_dates) >= 14:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 2 for {lead['name']}: sender {email} completed 14-day warmup.", lead["id"], campaign_id)
                                    continue
                                
                                # Check daily warmup limit
                                today_str = datetime.date.today().isoformat()
                                if today_str in sent_dates:
                                    day = len(sent_dates)
                                else:
                                    day = len(sent_dates) + 1
                                    
                                default_schedule = {
                                    "1": 5, "2": 8, "3": 10, "4": 12, "5": 15, "6": 18, "7": 20,
                                    "8": 25, "9": 30, "10": 35, "11": 40, "12": 45, "13": 50, "14": 50
                                }
                                warmup_schedule = settings.get("warmup_schedule", default_schedule)
                                daily_limit = int(warmup_schedule.get(str(day)) or warmup_schedule.get(day) or 50)
                                sent_today = prog.get("sent_today", 0)
                                
                                if sent_today >= daily_limit:
                                    # Mailbox hit daily limit, skip this follow-up for today
                                    continue

                            lead_manager.update_lead_status(
                                lead["id"], "Sending", "Sending Follow-up 2", 
                                f"Sending follow-up 2 from {selected_account['email']} (no reply detected)",
                                campaign_id=campaign_id
                            )
                            
                            draft = lead["email_drafts"]["follow_up_2"]
                            subject = draft["subject"]
                            body = draft["body"].replace("[Sender Name]", selected_account.get("sender_name", "Go4Database Agent"))
                            
                            try:
                                sent_real = send_email_via_smtp(selected_account, lead["email"], subject, body)
                                if sent_real:
                                    details = f"Follow-up 2 sent via SMTP to {lead['email']} (Sender: {selected_account['email']})"
                                else:
                                    details = f"[SIMULATED] Follow-up 2 sent to {lead['email']} (Sender: {selected_account['email']})"
                                    
                                new_history = list(lead["history"]) + [{
                                    "timestamp": now.isoformat(),
                                    "action": "Email Sent (Follow-up 2)",
                                    "details": details + f"\nSubject: {subject}"
                                }]
                                lead_manager.update_lead_sent_state(
                                    lead["id"], "Follow_Up_2_Sent", now.isoformat(), 3, new_history,
                                    sender_account_id=selected_account["id"], campaign_id=campaign_id
                                )
                                lead_manager.add_log("INFO", f"Sent follow-up 2 to {lead['name']} ({lead['company']}) from {selected_account['email']}.", lead["id"], campaign_id)
                                
                            except Exception as e:
                                import smtplib
                                if isinstance(e, smtplib.SMTPRecipientsRefused):
                                    lead_manager.update_lead_status(
                                        lead["id"], "Junk", "Bounced (Immediate)", 
                                        f"SMTP server refused recipient address (wrong email): {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 2 to {lead['name']} ({lead['email']}): Recipient refused. Marked as Junk.", lead["id"], campaign_id)
                                else:
                                    lead_manager.update_lead_status(
                                        lead["id"], "Follow_Up_1_Sent", "Send Error",
                                        f"Failed to send follow-up 2: {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 2 to {lead['name']}: {str(e)}", lead["id"], campaign_id)
                            
                            lead_processed = True
                            time.sleep(int(settings.get("min_delay", 5)))
                            break

                    # 4. Process Auto Follow-up 3
                    if lead["status"] == "Follow_Up_2_Sent" and lead.get("sequence_step") == 3:
                        last_sent = datetime.datetime.fromisoformat(lead["last_sent_time"])
                        delay_hours = float(settings.get("followup_delay_3_hours", 48))
                        delay_seconds = int(delay_hours * 3600)
                        
                        if (now - last_sent).total_seconds() >= delay_seconds:
                            sender_account_id = lead.get("sender_account_id", "primary")
                            selected_account = get_sender_account_by_id(settings, sender_account_id)
                            
                            # Check Global Limit
                            global_limit = int(settings.get("daily_limit", 50))
                            sent_today_global = sum(1 for c_temp in campaigns for l in lead_manager.get_leads(campaign_id=c_temp["id"]) 
                                                    for h in l.get("history", []) if h.get("action", "").startswith("Email Sent") 
                                                    and datetime.datetime.fromisoformat(h.get("timestamp", "2000-01-01")).date() == now.date())
                            if sent_today_global >= global_limit:
                                 lead_manager.add_log("SYSTEM", f"Reached global daily email limit of {global_limit}. Pausing campaign.", None, campaign_id)
                                 lead_manager.set_campaign_running(False, campaign_id=campaign_id)
                                 break

                            # Check per-mailbox warmup & cap limits
                            email = selected_account.get("email", "").lower().strip()
                            if email != "simulated@example.com":
                                warmup_progress = calculate_warmup_progress(lead_manager.state)
                                prog = warmup_progress.get(email, {})
                                
                                # Check total cap
                                total_sent = prog.get("total_sent", 0)
                                warmup_total_cap = int(settings.get("warmup_total_cap", 50))
                                if total_sent >= warmup_total_cap:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 3 for {lead['name']}: sender {email} completed warmup (reached total cap of {warmup_total_cap}).", lead["id"], campaign_id)
                                    continue
                                
                                # Check warmup days cap (14 days)
                                sent_dates = prog.get("dates", [])
                                if len(sent_dates) >= 14:
                                    lead_manager.add_log("SYSTEM", f"Skipping follow-up 3 for {lead['name']}: sender {email} completed 14-day warmup.", lead["id"], campaign_id)
                                    continue
                                
                                # Check daily warmup limit
                                today_str = datetime.date.today().isoformat()
                                if today_str in sent_dates:
                                    day = len(sent_dates)
                                else:
                                    day = len(sent_dates) + 1
                                    
                                default_schedule = {
                                    "1": 5, "2": 8, "3": 10, "4": 12, "5": 15, "6": 18, "7": 20,
                                    "8": 25, "9": 30, "10": 35, "11": 40, "12": 45, "13": 50, "14": 50
                                }
                                warmup_schedule = settings.get("warmup_schedule", default_schedule)
                                daily_limit = int(warmup_schedule.get(str(day)) or warmup_schedule.get(day) or 50)
                                sent_today = prog.get("sent_today", 0)
                                
                                if sent_today >= daily_limit:
                                    # Mailbox hit daily limit, skip this follow-up for today
                                    continue

                            lead_manager.update_lead_status(
                                lead["id"], "Sending", "Sending Follow-up 3", 
                                f"Sending final follow-up 3 from {selected_account['email']} (no reply detected)",
                                campaign_id=campaign_id
                            )
                            
                            drafts = lead.get("email_drafts") or {}
                            draft = drafts.get("follow_up_3")
                            if not draft:
                                draft = {
                                    "subject": f"Closing the loop / {lead.get('company')}",
                                    "body": f"Hi {lead.get('name', 'there')},\n\nI haven't heard back, so I'll assume that growing your database isn't a priority for {lead.get('company')} right now.\n\nBest,\n[Sender Name]"
                                }
                            subject = draft["subject"]
                            body = draft["body"].replace("[Sender Name]", selected_account.get("sender_name", "Go4Database Agent"))
                            
                            try:
                                sent_real = send_email_via_smtp(selected_account, lead["email"], subject, body)
                                if sent_real:
                                    details = f"Final Follow-up 3 sent via SMTP to {lead['email']} (Sender: {selected_account['email']})"
                                else:
                                    details = f"[SIMULATED] Final Follow-up 3 sent to {lead['email']} (Sender: {selected_account['email']})"
                                    
                                new_history = list(lead["history"]) + [{
                                    "timestamp": now.isoformat(),
                                    "action": "Email Sent (Follow-up 3 / Close)",
                                    "details": details + f"\nSubject: {subject}"
                                }]
                                lead_manager.update_lead_sent_state(
                                    lead["id"], "Follow_Up_3_Sent", now.isoformat(), 4, new_history,
                                    sender_account_id=selected_account["id"], campaign_id=campaign_id
                                )
                                lead_manager.add_log("INFO", f"Sent final follow-up 3 to {lead['name']} ({lead['company']}) from {selected_account['email']}. Campaign completed for lead.", lead["id"], campaign_id)
                                
                            except Exception as e:
                                import smtplib
                                if isinstance(e, smtplib.SMTPRecipientsRefused):
                                    lead_manager.update_lead_status(
                                        lead["id"], "Junk", "Bounced (Immediate)", 
                                        f"SMTP server refused recipient address (wrong email): {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 3 to {lead['name']} ({lead['email']}): Recipient refused. Marked as Junk.", lead["id"], campaign_id)
                                else:
                                    lead_manager.update_lead_status(
                                        lead["id"], "Follow_Up_2_Sent", "Send Error",
                                        f"Failed to send follow-up 3: {str(e)}",
                                        campaign_id=campaign_id
                                    )
                                    lead_manager.add_log("ERROR", f"Failed to send follow-up 3 to {lead['name']}: {str(e)}", lead["id"], campaign_id)
                            
                            lead_processed = True
                            time.sleep(int(settings.get("min_delay", 5)))
                            break
        
        # Poll every 2 seconds for outbound eligibility
        time.sleep(2)

@app.on_event("startup")
def startup_event():
    global worker_thread, worker_running
    worker_running = True
    worker_thread = threading.Thread(target=campaign_worker_loop, daemon=True)
    worker_thread.start()

@app.on_event("shutdown")
def shutdown_event():
    global worker_running
    worker_running = False

# Auth and User Management Routes
class LoginPayload(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

class UserPayload(BaseModel):
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    password: str
    role: str
    permissions: Optional[List[str]] = []

class AssignLeadPayload(BaseModel):
    assigned_to: Optional[str] = None

@app.post("/api/auth/login")
def auth_login(payload: LoginPayload):
    email = payload.email or payload.username
    password = payload.password
    
    if not email:
        raise HTTPException(status_code=422, detail="Email or username is required")
        
    # Standardize input for default admin
    if email.lower() in ("admin", "admin@admin.com"):
        target_email = "admin@admin.com"
    else:
        target_email = email
    
    users = lead_manager.state.get("users", [])
    user = next((u for u in users if (
        u.get("email") == target_email or 
        u.get("username") == target_email or 
        u.get("email") == email or 
        u.get("username") == email
    ) and u["password"] == password), None)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    token = str(uuid.uuid4())
    active_sessions[token] = user
    
    perms = user.get("permissions", [])
    if user.get("role") == "Admin":
        perms = ["sessions", "overview", "import", "leads", "hot-leads", "replies", "agent-training", "hyper-agent", "email-preview", "warmup", "settings"]
        
    return {
        "status": "success",
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user.get("email") or user.get("username"),
            "role": user["role"],
            "permissions": perms
        }
    }

@app.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    perms = user.get("permissions", [])
    if user.get("role") == "Admin":
        perms = ["sessions", "overview", "import", "leads", "hot-leads", "replies", "agent-training", "hyper-agent", "email-preview", "warmup", "settings"]
        
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user.get("email") or user.get("username"),
        "role": user["role"],
        "permissions": perms
    }

@app.post("/api/auth/logout")
def auth_logout(x_session_token: Optional[str] = Header(None), token: Optional[str] = None):
    tok = x_session_token or token
    if tok in active_sessions:
        del active_sessions[tok]
    return {"status": "success"}

@app.get("/api/users")
def list_users(user: dict = Depends(get_current_user)):
    users = lead_manager.state.get("users", [])
    if user.get("role") == "Admin":
        return users
    else:
        return [{"id": u["id"], "name": u["name"], "email": u.get("email") or u.get("username"), "role": u["role"], "permissions": u.get("permissions", [])} for u in users]

@app.post("/api/users/add")
def add_user(payload: UserPayload, user: dict = Depends(verify_admin)):
    email = payload.email or payload.username
    if not email:
        raise HTTPException(status_code=400, detail="Email or username is required")
        
    users = lead_manager.state.get("users", [])
    if any((u.get("email") == email or u.get("username") == email) for u in users):
        raise HTTPException(status_code=400, detail="Email/username already exists")
        
    new_user = {
        "id": "user_" + str(uuid.uuid4())[:8],
        "name": payload.name,
        "email": email,
        "password": payload.password,
        "role": payload.role,
        "permissions": payload.permissions or []
    }
    
    lead_manager.add_user(new_user)
    return {"status": "success", "user": new_user}

@app.post("/api/users/delete/{user_id}")
def delete_user(user_id: str, user: dict = Depends(verify_admin)):
    if user_id == "admin_user":
        raise HTTPException(status_code=400, detail="Cannot delete default admin user")
        
    users = lead_manager.state.get("users", [])
    user_to_delete = next((u for u in users if u["id"] == user_id), None)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
        
    lead_manager.delete_user(user_id)
    # Clear active sessions
    for tok, session_user in list(active_sessions.items()):
        if session_user["id"] == user_id:
            del active_sessions[tok]
            
    return {"status": "success"}

@app.post("/api/leads/assign/{lead_id}")
def assign_lead(lead_id: str, payload: AssignLeadPayload, user: dict = Depends(get_current_user)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    lead = lead_manager.get_lead(lead_id, campaign_id=active_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    with lead_manager.lock:
        lead["assigned_to"] = payload.assigned_to
        assigned_user_name = "Unassigned"
        if payload.assigned_to:
            users = lead_manager.state.get("users", [])
            target_user = next((u for u in users if u["id"] == payload.assigned_to), None)
            if target_user:
                assigned_user_name = target_user["name"]
                
        lead["history"].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "action": "Lead Assigned",
            "details": f"Lead assigned to {assigned_user_name} by {user['name']}."
        })
        lead_manager.save_state()
        
    return {"status": "success", "lead": lead}

# API Routes
@app.get("/api/settings")
def get_settings(user: dict = Depends(verify_admin)):
    return lead_manager.get_settings()

@app.post("/api/settings")
def update_settings(settings: dict, user: dict = Depends(verify_admin)):
    lead_manager.update_settings(settings)
    return {"status": "success", "settings": lead_manager.get_settings()}

@app.get("/api/leads")
def get_leads(user: dict = Depends(get_current_user)):
    leads = lead_manager.get_leads()
    if user.get("role") == "Sales Rep":
        hot_statuses = {"Interested", "Replied", "Not_Interested", "OOO", "Wrong_Contact", "Sample_Approval"}
        leads = [l for l in leads if l.get("status") in hot_statuses]
    return leads

@app.post("/api/leads/delete/{lead_id}")
def delete_lead(lead_id: str, user: dict = Depends(verify_admin)):
    with lead_manager.lock:
        campaign_id = lead_manager.find_campaign_id_for_lead(lead_id)
        if campaign_id:
            campaign = lead_manager.state["campaigns"][campaign_id]
            campaign["leads"] = [l for l in campaign["leads"] if l["id"] != lead_id]
            lead_manager.update_campaign_stats_unsafe(campaign_id)
            lead_manager.save_state()
            return {"status": "success"}
    raise HTTPException(status_code=404, detail="Lead not found")

@app.post("/api/leads/toggle-approve/{lead_id}")
def toggle_approve(lead_id: str, user: dict = Depends(verify_admin)):
    with lead_manager.lock:
        lead = lead_manager.get_lead(lead_id)
        if lead:
            lead["is_approved"] = not lead.get("is_approved", False)
            lead_manager.save_state()
            return {"status": "success"}
    raise HTTPException(status_code=404, detail="Lead not found")


class SetStatusPayload(BaseModel):
    status: str
    action: Optional[str] = None
    details: Optional[str] = None

@app.post("/api/leads/set-status/{lead_id}")
def set_lead_status(lead_id: str, payload: SetStatusPayload, user: dict = Depends(get_current_user)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    lead = lead_manager.get_lead(lead_id, campaign_id=active_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    status = payload.status
    action = payload.action or "Manual Update"
    details = payload.details or f"Lead status updated manually to {status}."
    
    lead_manager.update_lead_status(lead_id, status, action, details, campaign_id=active_id)
    return {"status": "success"}

class CustomInstructionsPayload(BaseModel):
    custom_agent_instructions: str

@app.post("/api/leads/custom-instructions/{lead_id}")
def update_lead_custom_instructions(lead_id: str, payload: CustomInstructionsPayload, user: dict = Depends(get_current_user)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    lead = lead_manager.get_lead(lead_id, campaign_id=active_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    with lead_manager.lock:
        lead["custom_agent_instructions"] = payload.custom_agent_instructions.strip()
        lead["history"].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "action": "Agent Instructions Updated",
            "details": f"Hyper-personalized guidelines updated by {user['name']}."
        })
        lead_manager.save_state()
        
    return {"status": "success", "lead": lead}

@app.post("/api/leads/upload")
async def upload_leads(
    file: UploadFile = File(None),
    pasted_data: str = Form(None),
    campaign_name: str = Form(None),
    start_date: Optional[str] = Form(None),
    user: dict = Depends(verify_admin)
):
    if not campaign_name:
        if file:
            campaign_name = file.filename
        elif pasted_data:
            campaign_name = f"Pasted Leads - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        else:
            campaign_name = "New Campaign"

    actual_start = start_date.strip() if start_date and start_date.strip() else None
    campaign_id = lead_manager.create_campaign(campaign_name, start_date=actual_start)
    lead_manager.set_active_campaign(campaign_id)
    
    leads_list = []
    
    # 1. Parse from file
    if file:
        content = await file.read()
        filename = file.filename.lower()
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(io.StringIO(content.decode('utf-8', errors='ignore')))
            elif filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(io.BytesIO(content))
            else:
                lead_manager.delete_campaign(campaign_id)
                raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")
            
            # Normalize headers
            df.columns = [c.strip().lower().replace(' ', '_').replace('/', '_') for c in df.columns]
            
            # Map columns to lead format
            leads_list = df.to_dict('records')
            
        except Exception as e:
            lead_manager.add_log("ERROR", f"Failed to parse uploaded file: {str(e)}", None, campaign_id)
            lead_manager.delete_campaign(campaign_id)
            raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
            
    # 2. Parse from pasted data (CSV / TSV format)
    elif pasted_data:
        try:
            lines = [line.strip() for line in pasted_data.strip().split('\n') if line.strip()]
            if lines:
                # Detect delimiter (tab or comma)
                delimiter = '\t' if '\t' in lines[0] else ','
                header = [h.strip().lower().replace(' ', '_') for h in lines[0].split(delimiter)]
                
                for line in lines[1:]:
                    vals = [v.strip() for v in line.split(delimiter)]
                    # Pad list if it is shorter than headers
                    while len(vals) < len(header):
                        vals.append("")
                    lead_dict = dict(zip(header, vals))
                    leads_list.append(lead_dict)
        except Exception as e:
            lead_manager.add_log("ERROR", f"Failed to parse pasted table: {str(e)}", None, campaign_id)
            lead_manager.delete_campaign(campaign_id)
            raise HTTPException(status_code=400, detail=f"Failed to parse pasted table: {str(e)}")
            
    else:
        lead_manager.delete_campaign(campaign_id)
        raise HTTPException(status_code=400, detail="No lead data provided.")

    if not leads_list:
        lead_manager.delete_campaign(campaign_id)
        raise HTTPException(status_code=400, detail="No valid lead records found.")

    # Standardize lead dictionary keys for ingestion
    standardized_leads = []
    for raw in leads_list:
        std = {
            "company": raw.get("company_name") or raw.get("company") or raw.get("organization") or "",
            "name": raw.get("full_name") or raw.get("person_name") or raw.get("name") or raw.get("contact") or raw.get("contact_name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip() or "",
            "title": raw.get("job_title") or raw.get("title") or raw.get("position") or raw.get("role") or raw.get("headline") or "",
            "email": raw.get("email") or raw.get("email_address") or raw.get("personal_email") or "",
            "company_size": str(raw.get("company_size") or raw.get("size") or ""),
            "industry": raw.get("industry") or raw.get("icp_industry") or raw.get("sector") or "",
            "location": raw.get("location") or raw.get("city") or raw.get("state") or raw.get("country") or "",
            "branch": raw.get("branch") or raw.get("department") or "",
            "notes": raw.get("notes") or raw.get("description") or "",
            "icp_tags": raw.get("icp_tags") or raw.get("tags") or ""
        }
        if std["email"]:
            standardized_leads.append(std)

    if not standardized_leads:
        lead_manager.delete_campaign(campaign_id)
        raise HTTPException(status_code=400, detail="No leads with valid email addresses found.")

    added = lead_manager.add_leads(standardized_leads, campaign_id=campaign_id)
    return {"status": "success", "added_count": added}


# Background AI analysis task
def run_ai_analysis_background(lead_id: str, api_key: str, campaign_id: Optional[str] = None):
    lead = lead_manager.get_lead(lead_id, campaign_id=campaign_id)
    if not lead:
        return
        
    lead_manager.update_lead_status(lead_id, "Analyzing", "AI Analysis Started", "Running Go4Database matching rules & copy creation...", campaign_id=campaign_id)
    
    try:
        matched_segment, drafts, score = analyze_and_draft(lead, api_key)
        lead_manager.update_lead_drafts(lead_id, drafts, matched_segment, score, campaign_id=campaign_id)
    except Exception as e:
        lead_manager.update_lead_status(lead_id, "Pending", "AI Analysis Failed", str(e), campaign_id=campaign_id)
        lead_manager.add_log("ERROR", f"AI Agent analysis failed for lead {lead['name']}: {str(e)}", lead_id, campaign_id=campaign_id)

@app.post("/api/leads/analyze")
def trigger_analysis(background_tasks: BackgroundTasks, user: dict = Depends(verify_admin)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    leads = lead_manager.get_leads(campaign_id=active_id)
    settings = lead_manager.get_settings()
    api_key = settings.get("gemini_api_key", "")
    
    pending_leads = [l for l in leads if l["status"] in ["Pending", "Analyzing"]]
    
    if not pending_leads:
        return {"status": "no_pending_leads"}
        
    for lead in pending_leads:
        with lead_manager.lock:
            if lead["status"] == "Analyzing":
                continue
            lead["status"] = "Analyzing"
            
        background_tasks.add_task(run_ai_analysis_background, lead["id"], api_key, active_id)
        
    lead_manager.add_log("SYSTEM", f"Triggered AI Agent analysis pipeline for {len(pending_leads)} leads.", None, active_id)
    return {"status": "success", "count": len(pending_leads)}


@app.post("/api/leads/update-email")
def update_email_draft(payload: dict, user: dict = Depends(verify_admin)):
    lead_id = payload.get("lead_id")
    email_type = payload.get("email_type") # initial_pitch, follow_up_1, follow_up_2
    subject = payload.get("subject")
    body = payload.get("body")
    
    if not lead_id or not email_type or subject is None or body is None:
        raise HTTPException(status_code=400, detail="Missing required parameters.")
        
    lead_manager.update_lead_email_body(lead_id, email_type, subject, body)
    return {"status": "success"}


@app.post("/api/campaign/start")
def start_campaign(background_tasks: BackgroundTasks, campaign_id: Optional[str] = None, user: dict = Depends(verify_admin)):
    target_id = campaign_id or lead_manager.state.get("active_campaign_id", "default")
    lead_manager.set_campaign_running(True, campaign_id=target_id)
    
    # Automatically trigger analysis for any Pending leads in the background
    leads = lead_manager.get_leads(campaign_id=target_id)
    settings = lead_manager.get_settings()
    api_key = settings.get("gemini_api_key", "")
    
    pending_leads = [l for l in leads if l["status"] in ["Pending", "Analyzing"]]
    for lead in pending_leads:
        with lead_manager.lock:
            if lead["status"] == "Analyzing":
                continue
            lead["status"] = "Analyzing"
        background_tasks.add_task(run_ai_analysis_background, lead["id"], api_key, target_id)
        
    if pending_leads:
        lead_manager.add_log("SYSTEM", f"Campaign started. Auto-triggering AI analysis for {len(pending_leads)} pending leads.", None, target_id)
        
    return {"status": "success", "campaign_status": lead_manager.get_campaign_status(campaign_id=target_id)}


@app.post("/api/campaign/pause")
def pause_campaign(campaign_id: Optional[str] = None, user: dict = Depends(verify_admin)):
    target_id = campaign_id or lead_manager.state.get("active_campaign_id", "default")
    lead_manager.set_campaign_running(False, campaign_id=target_id)
    return {"status": "success", "campaign_status": lead_manager.get_campaign_status(campaign_id=target_id)}


@app.post("/api/campaign/reset")
def reset_campaign(user: dict = Depends(verify_admin)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    lead_manager.clear_all(campaign_id=active_id)
    return {"status": "success"}


@app.post("/api/campaign/reset-warmup")
def reset_campaign_warmup(user: dict = Depends(verify_admin)):
    lead_manager.reset_warmup_stats()
    return {"status": "success"}


@app.get("/api/campaign/status")
def get_campaign_status(user: dict = Depends(verify_admin)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    return lead_manager.get_campaign_status(campaign_id=active_id)


@app.get("/api/campaign/logs")
def get_campaign_logs(user: dict = Depends(verify_admin)):
    active_id = lead_manager.state.get("active_campaign_id", "default")
    return lead_manager.get_logs(limit=100, campaign_id=active_id)


def calculate_warmup_progress(state: dict) -> dict:
    import re
    import datetime
    
    progress = {}
    campaigns = state.get("campaigns", {})
    settings = state.get("settings", {})
    
    primary_email = (settings.get("sender_email") or settings.get("smtp_user") or "primary@example.com").lower().strip()
    today_str = datetime.date.today().isoformat()
    warmup_total_cap = int(settings.get("warmup_total_cap", 50))
    
    # Pre-populate with historical counts and all active accounts
    historical_send_counts = settings.get("historical_send_counts", {})
    for email, count in historical_send_counts.items():
        email_clean = email.lower().strip()
        if email_clean not in progress:
            progress[email_clean] = {
                "completed_days": 0,
                "is_completed": False,
                "dates": set(),
                "total_sent": int(count),
                "sent_today": 0
            }
            
    try:
        enabled_accounts = get_all_enabled_sender_accounts(settings)
        for acc in enabled_accounts:
            email_clean = acc.get("email", "").lower().strip()
            if email_clean and email_clean not in progress:
                progress[email_clean] = {
                    "completed_days": 0,
                    "is_completed": False,
                    "dates": set(),
                    "total_sent": int(historical_send_counts.get(email_clean, 0)),
                    "sent_today": 0
                }
    except Exception as e:
        print(f"Error in calculate_warmup_progress pre-populating accounts: {e}")
        
    for c_id, campaign in campaigns.items():
        leads = campaign.get("leads", [])
        for lead in leads:
            history = lead.get("history", [])
            for event in history:
                action = event.get("action", "")
                details = event.get("details", "")
                ts_str = event.get("timestamp", "")
                
                if "Email Sent" in action:
                    match = re.search(r"\(Sender:\s*([^\s)]+)\)", details)
                    if match:
                        sender_email = match.group(1).strip().lower()
                    else:
                        acc_id = lead.get("sender_account_id")
                        if acc_id == "primary":
                            sender_email = primary_email
                        elif acc_id:
                            accounts = settings.get("sender_accounts", [])
                            acc = next((a for a in accounts if a.get("id") == acc_id), None)
                            if acc:
                                sender_email = (acc.get("email") or acc.get("smtp_user") or acc_id).lower().strip()
                            else:
                                sender_email = acc_id.lower().strip()
                        else:
                            sender_email = primary_email
                    
                    if sender_email in {"primary@example.com", "rota@example.com", "rotb@example.com"}:
                        continue
                        
                    if sender_email not in progress:
                        progress[sender_email] = {
                            "completed_days": 0,
                            "is_completed": False,
                            "dates": set(),
                            "total_sent": int(historical_send_counts.get(sender_email, 0)),
                            "sent_today": 0
                        }
                    
                    progress[sender_email]["total_sent"] += 1
                    
                    try:
                        dt = datetime.datetime.fromisoformat(ts_str)
                        date_str = dt.date().isoformat()
                        progress[sender_email]["dates"].add(date_str)
                        if date_str == today_str:
                            progress[sender_email]["sent_today"] += 1
                    except Exception:
                        pass
                        
    for sender, data in progress.items():
        sorted_dates = sorted(list(data["dates"]))
        data["dates"] = sorted_dates
        data["completed_days"] = len(sorted_dates)
        data["is_completed"] = (len(sorted_dates) >= 14 or data["total_sent"] >= warmup_total_cap)
        
    return progress


@app.get("/api/campaign/warmup")
def get_campaign_warmup(user: dict = Depends(verify_admin)):
    import re
    from collections import Counter
    
    sent_counts = Counter()
    
    campaigns = lead_manager.state.get("campaigns", {})
    settings = lead_manager.get_settings()
    
    # Add historical counts
    historical_send_counts = settings.get("historical_send_counts", {})
    for email, count in historical_send_counts.items():
        sent_counts[email.lower().strip()] += int(count)
        
    for c_id, campaign in campaigns.items():
        leads = campaign.get("leads", [])
        for lead in leads:
            history = lead.get("history", [])
            for event in history:
                action = event.get("action", "")
                details = event.get("details", "")
                
                if "Email Sent" in action:
                    match = re.search(r"\(Sender:\s*([^\s)]+)\)", details)
                    if match:
                        sender_email = match.group(1).strip()
                    else:
                        acc_id = lead.get("sender_account_id")
                        if acc_id == "primary":
                            sender_email = settings.get("sender_email") or settings.get("smtp_user") or "primary@example.com"
                        elif acc_id:
                            accounts = settings.get("sender_accounts", [])
                            acc = next((a for a in accounts if a.get("id") == acc_id), None)
                            if acc:
                                sender_email = acc.get("email") or acc.get("smtp_user") or acc_id
                            else:
                                sender_email = acc_id
                        else:
                            sender_email = settings.get("sender_email") or settings.get("smtp_user") or "primary@example.com"
                    
                    sender_email = sender_email.lower().strip()
                    if sender_email in {"primary@example.com", "rota@example.com", "rotb@example.com"}:
                        continue
                        
                    sent_counts[sender_email] += 1
                    
    progress_map = calculate_warmup_progress(lead_manager.state)
    
    # Ensure all configured accounts are present in progress_map and sent_counts
    for account in get_all_enabled_sender_accounts(settings):
        email_clean = account["email"].lower().strip()
        if email_clean in {"primary@example.com", "rota@example.com", "rotb@example.com"}:
            continue
        if email_clean not in progress_map:
            progress_map[email_clean] = {
                "completed_days": 0,
                "is_completed": False,
                "dates": []
            }
        if email_clean not in sent_counts:
            sent_counts[email_clean] = 0
            
    # Ensure all senders in counts also exist in progress_map (fallback)
    for sender in sent_counts:
        s_lower = sender.lower().strip()
        if s_lower not in progress_map:
            progress_map[s_lower] = {
                "completed_days": 0,
                "is_completed": False,
                "dates": []
            }
            
    return {
        "counts": dict(sent_counts),
        "warmup_progress": progress_map,
        "total_sends": sum(sent_counts.values())
    }



@app.post("/api/test/reload-state")
def reload_state(user: dict = Depends(verify_admin)):
    lead_manager.load_state()
    return {"status": "success", "message": "State reloaded from disk"}


# Multi-Session Campaign Endpoints
@app.get("/api/campaigns")
def list_campaigns(user: dict = Depends(verify_admin)):
    return lead_manager.get_campaigns()


@app.get("/api/campaigns/active")
def get_active_campaign(user: dict = Depends(verify_admin)):
    return {"active_campaign_id": lead_manager.state.get("active_campaign_id", "default")}


@app.post("/api/campaigns/active/{campaign_id}")
def set_active_campaign(campaign_id: str, user: dict = Depends(verify_admin)):
    lead_manager.set_active_campaign(campaign_id)
    return {"status": "success", "active_campaign_id": lead_manager.state.get("active_campaign_id")}


@app.post("/api/campaigns/delete/{campaign_id}")
def delete_campaign_session(campaign_id: str, user: dict = Depends(verify_admin)):
    lead_manager.delete_campaign(campaign_id)
    return {"status": "success"}


def handle_received_reply(lead: dict, reply_body: str, campaign_id: str, is_simulated: bool = False) -> dict:
    lead_id = lead["id"]
    with lead_manager.lock:
        reply_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "sender": lead["email"],
            "body": reply_body
        }
        if "replies" not in lead or lead["replies"] is None:
            lead["replies"] = []
        lead["replies"].append(reply_entry)
        lead["status"] = "Replied"
        
        prefix = "[SIMULATED]" if is_simulated else "[REAL]"
        lead["history"].append({
            "timestamp": datetime.datetime.now().isoformat(),
            "action": "Reply Received",
            "details": f"{prefix} message: \"{reply_body[:100]}...\""
        })
        lead_manager.add_log_unsafe("INFO", f"Reply received from {lead['name']} ({lead['company']}) {prefix}", lead_id, campaign_id)
        lead_manager.update_campaign_stats_unsafe(campaign_id)
        lead_manager.save_state()

    # Process reply classification using AI
    settings = lead_manager.get_settings()
    api_key = settings.get("gemini_api_key", "")
    
    def process_reply_logic():
        try:
            result = qualify_and_draft_reply(
                lead, 
                reply_body, 
                api_key, 
                sdr_training=settings.get("sdr_training"),
                sdr_persona=settings.get("sdr_persona")
            )
            stage = result.get("lead_stage", "MQL")
            score = result.get("qualification_score", 50)
            pain_points = result.get("pain_points", [])
            buying_intent = result.get("buying_intent", "Medium")
            next_action = result.get("next_action", "Nurture lead")
            followup_text = result.get("response_to_send", "")
            
            lead_manager.add_log("AGENT", f"Classified reply from {lead['name']}: {stage.upper()}. Score: {score}/100. Intent: {buying_intent}.", lead_id, campaign_id=campaign_id)
            
            with lead_manager.lock:
                lead["lead_stage"] = stage
                lead["qualification_score"] = score
                lead["pain_points"] = pain_points
                lead["buying_intent"] = buying_intent
                lead["next_action"] = next_action
                
                initial_subject = "Outreach"
                if lead.get("email_drafts") and lead["email_drafts"].get("initial_pitch"):
                    initial_subject = lead["email_drafts"]["initial_pitch"].get("subject", "Outreach")
                
                # Map standard category outputs to state statuses
                if stage == "SQL":
                    lead["status"] = "Interested" # Treated as Hot lead in the app
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "SDR SQL Qualified",
                        "details": f"Lead qualified as SQL.\nScore: {score}\nBuying Intent: {buying_intent}\nPain Points: {', '.join(pain_points)}\nNext Action: {next_action}"
                    })
                    lead_manager.add_log("INFO", f"Lead {lead['name']} qualified as SQL (Hot).", lead_id, campaign_id=campaign_id)
                    
                elif stage == "Sample Approval":
                    lead["status"] = "Sample_Approval"
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "SDR Sample Approval Requested",
                        "details": f"Lead qualified as Sample Approval.\nScore: {score}\nBuying Intent: {buying_intent}\nPain Points: {', '.join(pain_points)}\nNext Action: {next_action}"
                    })
                    lead_manager.add_log("INFO", f"Lead {lead['name']} qualified for Sample Approval.", lead_id, campaign_id=campaign_id)
                    
                elif stage == "OOO":
                    lead["status"] = "OOO"
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "OOO Snooze",
                        "details": "Out of office message received. Snoozing automated follow-ups."
                    })
                    lead_manager.add_log("INFO", f"Snoozing campaigns for {lead['name']} (Out of Office).", lead_id, campaign_id=campaign_id)
                    
                elif stage == "Disqualified":
                    if "wrong" in next_action.lower() or "wrong" in followup_text.lower():
                        lead["status"] = "Wrong_Contact"
                        details_text = "Lead reported wrong contact. Stopped outbound sequence."
                        action_text = "Wrong Contact / Stopped"
                        log_msg = f"Stopped campaign for {lead['name']} (Wrong Contact)."
                    else:
                        lead["status"] = "Not_Interested"
                        details_text = "Lead marked not interested. Removed from outbound sequences."
                        action_text = "Not Interested / Stopped"
                        log_msg = f"Stopped outreach for {lead['name']} (Not Interested)."
                    
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": action_text,
                        "details": details_text
                    })
                    lead_manager.add_log("INFO", log_msg, lead_id, campaign_id=campaign_id)
                    
                else: # MQL / other
                    lead["status"] = "Replied"
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "SDR MQL Qualified",
                        "details": f"Lead qualified as MQL.\nScore: {score}\nBuying Intent: {buying_intent}\nPain Points: {', '.join(pain_points)}\nNext Action: {next_action}"
                    })
                    lead_manager.add_log("INFO", f"Lead {lead['name']} qualified as MQL (Replied).", lead_id, campaign_id=campaign_id)
                
                # If a follow-up response was generated, save it
                if followup_text:
                    if not lead.get("email_drafts"):
                        lead["email_drafts"] = {}
                    lead["email_drafts"]["reply_nurture"] = {
                        "subject": f"Re: {initial_subject}",
                        "body": followup_text
                    }
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "Custom Response Generated",
                        "details": f"Generated response to prospect:\n\n{followup_text}"
                    })
                    lead_manager.add_log("INFO", f"Custom reply draft generated for {lead['name']}.", lead_id, campaign_id=campaign_id)
                    
            lead_manager.update_campaign_stats_unsafe(campaign_id)
            lead_manager.save_state()
            
        except Exception as e:
            lead_manager.add_log("ERROR", f"Error classifying reply for {lead['name']}: {str(e)}", lead_id, campaign_id=campaign_id)
            
    threading.Thread(target=process_reply_logic, daemon=True).start()
    return lead

@app.post("/api/campaign/simulate-reply")
async def simulate_reply(payload: dict, user: dict = Depends(verify_admin)):
    lead_id = payload.get("lead_id")
    reply_body = payload.get("reply_body")
    
    if not lead_id or not reply_body:
        raise HTTPException(status_code=400, detail="Missing lead_id or reply_body")
        
    campaign_id = lead_manager.find_campaign_id_for_lead(lead_id)
    if not campaign_id:
        raise HTTPException(status_code=404, detail="Campaign not found for lead")
        
    lead = lead_manager.get_lead(lead_id, campaign_id=campaign_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    handle_received_reply(lead, reply_body, campaign_id, is_simulated=True)
    return {"status": "success", "message": "Reply injection started"}

# Serve Frontend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Fallback to public_html if frontend dir doesn't exist (production standard)
if not os.path.isdir(FRONTEND_DIR):
    public_html_dir = os.path.join(BASE_DIR, "public_html")
    if os.path.isdir(public_html_dir):
        FRONTEND_DIR = public_html_dir
    else:
        # If still not found, create a dummy directory to avoid uvicorn start crash
        os.makedirs(FRONTEND_DIR, exist_ok=True)

@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Go4Database Outreach API Backend is Running"}

app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")


