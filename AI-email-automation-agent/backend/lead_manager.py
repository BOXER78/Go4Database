import os
import json
import uuid
import datetime
import threading
import sqlite3
from typing import List, Dict, Any, Optional

# Resolve absolute paths based on project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)
DB_FILE = os.path.join(DB_DIR, "campaign_state.db")
STATE_FILE = os.path.join(BASE_DIR, "campaign_state.json")

class LeadManager:
    def __init__(self):
        self.lock = threading.RLock()
        from agent_logic import DEFAULT_SDR_PERSONA
        self.state = {
            "active_campaign_id": "default",
            "users": [
                {
                    "id": "admin_user",
                    "name": "Admin User",
                    "email": "admin@admin.com",
                    "password": "admin123",
                    "role": "Admin"
                }
            ],
            "settings": {
                "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
                "sdr_persona": DEFAULT_SDR_PERSONA,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "imap_server": "",
                "imap_port": 993,
                "sender_name": "Go4Database Sales Team",
                "sender_email": "",
                "daily_limit": 50,
                "min_delay": 5,  # seconds
                "max_delay": 15, # seconds
                "auto_followup_delay_days": 24,
                "automation_mode": False,
                "warmup_total_cap": 50,
                "allow_duplicate_leads": True,
                "pause_on_warmup_complete": False,
                "warmup_schedule": {
                    "1": 5, "2": 8, "3": 10, "4": 12, "5": 15, "6": 18, "7": 20,
                    "8": 25, "9": 30, "10": 35, "11": 40, "12": 45, "13": 50, "14": 50
                },
                "sdr_training": {
                    "customer_to_mql": "Understand the prospect's situation, their role, and company fit. Communicate naturally, professionally, and conversationally. Answer introductory questions, explore initial interest, and offer to prepare a custom sample list.",
                    "mql_to_sql": "Explore pain points (e.g. low conversions, outdated contacts, gatekeepers) and current outbound tools/workflow. Qualify on need and authority. Recommend a sales discussion / book a meeting.",
                    "sql_to_sample_approval": "Identify if the prospect asks for custom data samples (e.g. 'send me a sample list'). Ask clarifying questions about their target filters (industries, location, size) to compile the sample. Guide them to sample approval."
                }
            },
            "campaigns": {
                "default": {
                    "id": "default",
                    "name": "Default Session",
                    "created_at": datetime.datetime.now().isoformat(),
                    "leads": [],
                    "logs": [],
                    "campaign_status": {
                        "is_running": False,
                        "total_sent": 0,
                        "total_replies": 0,
                        "total_interested": 0,
                        "total_not_interested": 0,
                        "total_leads": 0
                    }
                }
            }
        }
        self.load_state()

    def _get_conn(self):
        return sqlite3.connect(DB_FILE)

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    password TEXT,
                    role TEXT,
                    permissions TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at TEXT,
                    campaign_status TEXT,
                    start_date TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT,
                    company TEXT,
                    name TEXT,
                    title TEXT,
                    email TEXT,
                    company_size TEXT,
                    industry TEXT,
                    location TEXT,
                    branch TEXT,
                    notes TEXT,
                    icp_tags TEXT,
                    status TEXT,
                    score INTEGER,
                    matched_segment TEXT,
                    email_drafts TEXT,
                    sequence_step INTEGER,
                    last_sent_time TEXT,
                    is_approved INTEGER,
                    custom_agent_instructions TEXT,
                    history TEXT,
                    replies TEXT,
                    last_action_date TEXT,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT,
                    timestamp TEXT,
                    level TEXT,
                    message TEXT,
                    lead_id TEXT,
                    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
                )
            """)
            
            # Safe Schema Migration Check
            try:
                cursor.execute("PRAGMA table_info(users)")
                user_cols = [col[1] for col in cursor.fetchall()]
                if "permissions" not in user_cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN permissions TEXT")
            except Exception as e:
                print(f"Migration error (users table): {e}")

            try:
                cursor.execute("PRAGMA table_info(campaigns)")
                camp_cols = [col[1] for col in cursor.fetchall()]
                if "start_date" not in camp_cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN start_date TEXT")
            except Exception as e:
                print(f"Migration error (campaigns table): {e}")

            try:
                cursor.execute("PRAGMA table_info(leads)")
                lead_cols = [col[1] for col in cursor.fetchall()]
                if "sender_account_id" not in lead_cols:
                    cursor.execute("ALTER TABLE leads ADD COLUMN sender_account_id TEXT")
            except Exception as e:
                print(f"Migration error (leads table): {e}")

            conn.commit()

    def _load_from_db(self) -> dict:
        state = {
            "active_campaign_id": "default",
            "users": [],
            "settings": {},
            "campaigns": {}
        }
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Load active_campaign_id
            cursor.execute("SELECT value FROM settings WHERE key = 'active_campaign_id'")
            row = cursor.fetchone()
            if row:
                state["active_campaign_id"] = json.loads(row["value"])
            
            # Load settings
            cursor.execute("SELECT key, value FROM settings WHERE key != 'active_campaign_id'")
            for r in cursor.fetchall():
                state["settings"][r["key"]] = json.loads(r["value"])
                
            # Load users
            cursor.execute("SELECT id, name, email, password, role, permissions FROM users")
            for r in cursor.fetchall():
                perms = []
                if r["permissions"]:
                    try:
                        perms = json.loads(r["permissions"])
                    except Exception:
                        perms = [p.strip() for p in r["permissions"].split(",") if p.strip()]
                state["users"].append({
                    "id": r["id"],
                    "name": r["name"],
                    "email": r["email"],
                    "password": r["password"],
                    "role": r["role"],
                    "permissions": perms
                })
                
            # Load campaigns
            cursor.execute("SELECT id, name, created_at, campaign_status, start_date FROM campaigns")
            for r in cursor.fetchall():
                c_id = r["id"]
                state["campaigns"][c_id] = {
                    "id": c_id,
                    "name": r["name"],
                    "created_at": r["created_at"],
                    "campaign_status": json.loads(r["campaign_status"]) if r["campaign_status"] else {},
                    "start_date": r["start_date"],
                    "leads": [],
                    "logs": []
                }
                
            # Load leads
            cursor.execute("""
                SELECT id, campaign_id, company, name, title, email, company_size, industry, location, branch, notes, icp_tags, 
                       status, score, matched_segment, email_drafts, sequence_step, last_sent_time, is_approved, 
                       custom_agent_instructions, history, replies, last_action_date, sender_account_id
                FROM leads
            """)
            for r in cursor.fetchall():
                c_id = r["campaign_id"]
                if c_id in state["campaigns"]:
                    state["campaigns"][c_id]["leads"].append({
                        "id": r["id"],
                        "company": r["company"],
                        "name": r["name"],
                        "title": r["title"],
                        "email": r["email"],
                        "company_size": r["company_size"],
                        "industry": r["industry"],
                        "location": r["location"],
                        "branch": r["branch"],
                        "notes": r["notes"],
                        "icp_tags": r["icp_tags"],
                        "status": r["status"],
                        "score": r["score"],
                        "matched_segment": json.loads(r["matched_segment"]) if r["matched_segment"] else None,
                        "email_drafts": json.loads(r["email_drafts"]) if r["email_drafts"] else None,
                        "sequence_step": r["sequence_step"],
                        "last_sent_time": r["last_sent_time"],
                        "is_approved": bool(r["is_approved"]),
                        "custom_agent_instructions": r["custom_agent_instructions"],
                        "history": json.loads(r["history"]) if r["history"] else [],
                        "replies": json.loads(r["replies"]) if r["replies"] else [],
                        "last_action_date": r["last_action_date"],
                        "sender_account_id": r["sender_account_id"] if "sender_account_id" in r.keys() and r["sender_account_id"] else "primary"
                    })
                    
            # Load logs (limit to 1000 per campaign)
            cursor.execute("SELECT campaign_id, timestamp, level, message, lead_id FROM logs ORDER BY id ASC")
            for r in cursor.fetchall():
                c_id = r["campaign_id"]
                if c_id in state["campaigns"]:
                    logs_list = state["campaigns"][c_id]["logs"]
                    logs_list.append({
                        "timestamp": r["timestamp"],
                        "level": r["level"],
                        "message": r["message"],
                        "lead_id": r["lead_id"]
                    })
                    if len(logs_list) > 1000:
                        state["campaigns"][c_id]["logs"] = logs_list[-1000:]
                        
        return state

    def load_state(self):
        with self.lock:
            self._init_db()
            
            # Check if database is empty by counting campaigns
            is_db_empty = False
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM campaigns")
                count = cursor.fetchone()[0]
                if count == 0:
                    is_db_empty = True
                    
            if is_db_empty:
                # DB is empty, try to migrate from json if it exists
                if os.path.exists(STATE_FILE):
                    try:
                        with open(STATE_FILE, "r") as f:
                            saved_state = json.load(f)
                            
                        # Load settings if present
                        if "settings" in saved_state:
                            self.state["settings"].update(saved_state["settings"])
                        
                        # Load users
                        if "users" in saved_state:
                            self.state["users"] = saved_state["users"]
                            # Migration from username to email
                            for u in self.state["users"]:
                                if "username" in u and "email" not in u:
                                    if u["username"] == "admin":
                                        u["email"] = "admin@admin.com"
                                    else:
                                        u["email"] = f"{u['username']}@example.com"
                                    del u["username"]
                        
                        # Load campaigns (including legacy format migration)
                        if "leads" in saved_state:
                            default_campaign = {
                                "id": "default",
                                "name": "Default Session",
                                "created_at": datetime.datetime.now().isoformat(),
                                "leads": saved_state["leads"],
                                "logs": saved_state.get("logs", []),
                                "campaign_status": {
                                    "is_running": False,
                                    "total_sent": 0,
                                    "total_replies": 0,
                                    "total_interested": 0,
                                    "total_not_interested": 0,
                                    "total_leads": 0
                                }
                            }
                            if "campaign_status" in saved_state:
                                default_campaign["campaign_status"].update(saved_state["campaign_status"])
                            self.state["campaigns"] = {"default": default_campaign}
                            self.state["active_campaign_id"] = "default"
                        else:
                            if "active_campaign_id" in saved_state:
                                self.state["active_campaign_id"] = saved_state["active_campaign_id"]
                            if "campaigns" in saved_state:
                                self.state["campaigns"] = saved_state["campaigns"]
                                
                        # Write all to SQLite database
                        with self._get_conn() as conn:
                            # 1. Save active_campaign_id
                            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_campaign_id', ?)", 
                                         (json.dumps(self.state["active_campaign_id"]),))
                            
                            # 2. Save settings
                            for k, v in self.state["settings"].items():
                                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                                             (k, json.dumps(v)))
                                
                            # 3. Save users
                            for u in self.state["users"]:
                                conn.execute("INSERT OR REPLACE INTO users (id, name, email, password, role, permissions) VALUES (?, ?, ?, ?, ?, ?)", 
                                             (u["id"], u["name"], u.get("email", ""), u.get("password", ""), u.get("role", ""), json.dumps(u.get("permissions", []))))
                                
                            # 4. Save campaigns, leads, logs
                            for c_id, campaign in self.state["campaigns"].items():
                                conn.execute("INSERT OR REPLACE INTO campaigns (id, name, created_at, campaign_status, start_date) VALUES (?, ?, ?, ?, ?)", 
                                             (c_id, campaign["name"], campaign["created_at"], json.dumps(campaign.get("campaign_status", {})), campaign.get("start_date")))
                                
                                for lead in campaign.get("leads", []):
                                    conn.execute("""
                                        INSERT OR REPLACE INTO leads (id, campaign_id, company, name, title, email, company_size, industry, location, branch, 
                                                           notes, icp_tags, status, score, matched_segment, email_drafts, sequence_step, 
                                                           last_sent_time, is_approved, custom_agent_instructions, history, replies, last_action_date, sender_account_id)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        lead["id"], c_id, lead.get("company", ""), lead.get("name", ""), lead.get("title", ""), lead.get("email", ""), 
                                        lead.get("company_size", ""), lead.get("industry", ""), lead.get("location", ""), lead.get("branch", ""), lead.get("notes", ""), lead.get("icp_tags", ""), 
                                        lead.get("status", "Pending"), lead.get("score", 0), json.dumps(lead.get("matched_segment")), json.dumps(lead.get("email_drafts")), 
                                        lead.get("sequence_step", 0), lead.get("last_sent_time"), int(lead.get("is_approved", False)), lead.get("custom_agent_instructions", ""), 
                                        json.dumps(lead.get("history", [])), json.dumps(lead.get("replies", [])), lead.get("last_action_date"), lead.get("sender_account_id", "primary")
                                    ))
                                
                                for log in campaign.get("logs", []):
                                    conn.execute("""
                                        INSERT INTO logs (campaign_id, timestamp, level, message, lead_id)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (c_id, log["timestamp"], log["level"], log["message"], log.get("lead_id")))
                            conn.commit()
                            
                        # Backup and delete legacy file
                        try:
                            os.rename(STATE_FILE, STATE_FILE + ".bak")
                            print(f"[MIGRATION SUCCESS] Migrated JSON to SQLite. Backup created at {STATE_FILE}.bak")
                        except Exception as backup_err:
                            print(f"[MIGRATION WARNING] Failed to rename JSON file: {backup_err}")
                            
                    except Exception as e:
                        print(f"Failed to migrate JSON state: {str(e)}")
                else:
                    # No JSON and empty DB, write initial default state to DB
                    with self._get_conn() as conn:
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_campaign_id', ?)", 
                                     (json.dumps(self.state["active_campaign_id"]),))
                        for k, v in self.state["settings"].items():
                            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                                         (k, json.dumps(v)))
                        for u in self.state["users"]:
                            conn.execute("INSERT OR REPLACE INTO users (id, name, email, password, role, permissions) VALUES (?, ?, ?, ?, ?, ?)", 
                                         (u["id"], u["name"], u["email"], u["password"], u["role"], json.dumps(u.get("permissions", []))))
                            
                        # Default campaign
                        campaign = self.state["campaigns"]["default"]
                        conn.execute("INSERT OR REPLACE INTO campaigns (id, name, created_at, campaign_status, start_date) VALUES (?, ?, ?, ?, ?)", 
                                     ("default", campaign["name"], campaign["created_at"], json.dumps(campaign["campaign_status"]), campaign.get("start_date")))
                        conn.commit()
                        
            # Finally, load everything from DB to memory
            self.state = self._load_from_db()

    def save_state(self):
        # State is written incrementally in mutators, so save_state is a no-op fallback
        pass

    def add_user(self, user: dict):
        with self.lock:
            if "users" not in self.state:
                self.state["users"] = []
            self.state["users"] = [u for u in self.state["users"] if u["id"] != user["id"]]
            self.state["users"].append(user)
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO users (id, name, email, password, role, permissions)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user["id"], user["name"], user["email"], user["password"], user["role"], json.dumps(user.get("permissions", []))))
                conn.commit()

    def delete_user(self, user_id: str):
        with self.lock:
            self.state["users"] = [u for u in self.state.get("users", []) if u["id"] != user_id]
            with self._get_conn() as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()

    def add_log_unsafe(self, level: str, message: str, lead_id: Optional[str] = None, campaign_id: Optional[str] = None):
        if not campaign_id:
            campaign_id = self.state.get("active_campaign_id", "default")
        
        if campaign_id not in self.state["campaigns"]:
            if self.state["campaigns"]:
                campaign_id = next(iter(self.state["campaigns"].keys()))
            else:
                print(f"[{level}] {message}")
                return
        
        campaign = self.state["campaigns"][campaign_id]
        if "logs" not in campaign:
            campaign["logs"] = []
            
        ts = datetime.datetime.now().isoformat()
        log_entry = {
            "timestamp": ts,
            "level": level,
            "message": message,
            "lead_id": lead_id
        }
        campaign["logs"].append(log_entry)
        if len(campaign["logs"]) > 1000:
            campaign["logs"] = campaign["logs"][-1000:]

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO logs (campaign_id, timestamp, level, message, lead_id)
                VALUES (?, ?, ?, ?, ?)
            """, (campaign_id, ts, level, message, lead_id))
            conn.commit()

    def add_log(self, level: str, message: str, lead_id: Optional[str] = None, campaign_id: Optional[str] = None):
        with self.lock:
            self.add_log_unsafe(level, message, lead_id, campaign_id)

    def get_logs(self, limit: int = 100, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                return self.state["campaigns"][campaign_id].get("logs", [])[-limit:]
            return []

    def get_settings(self) -> Dict[str, Any]:
        with self.lock:
            return self.state["settings"]

    def update_settings(self, new_settings: Dict[str, Any]):
        with self.lock:
            self.state["settings"].update(new_settings)
            if "gemini_api_key" in new_settings:
                os.environ["GEMINI_API_KEY"] = new_settings["gemini_api_key"]
            self.add_log_unsafe("INFO", "Campaign settings updated.", None, self.state.get("active_campaign_id"))
            
            with self._get_conn() as conn:
                for key, val in new_settings.items():
                    conn.execute("""
                        INSERT INTO settings (key, value)
                        VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """, (key, json.dumps(val)))
                conn.commit()

    def get_leads(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                return self.state["campaigns"][campaign_id].get("leads", [])
            return []

    def get_lead(self, lead_id: str, campaign_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            if campaign_id:
                if campaign_id in self.state["campaigns"]:
                    for lead in self.state["campaigns"][campaign_id].get("leads", []):
                        if lead["id"] == lead_id:
                            return lead
                return None
            
            active_id = self.state.get("active_campaign_id")
            if active_id and active_id in self.state["campaigns"]:
                for lead in self.state["campaigns"][active_id].get("leads", []):
                    if lead["id"] == lead_id:
                        return lead
            
            for cid, campaign in self.state["campaigns"].items():
                if cid == active_id:
                    continue
                for lead in campaign.get("leads", []):
                    if lead["id"] == lead_id:
                        return lead
        return None

    def find_campaign_id_for_lead(self, lead_id: str) -> Optional[str]:
        with self.lock:
            active_id = self.state.get("active_campaign_id")
            if active_id and active_id in self.state["campaigns"]:
                for lead in self.state["campaigns"][active_id].get("leads", []):
                    if lead["id"] == lead_id:
                        return active_id
            for cid, campaign in self.state["campaigns"].items():
                if cid == active_id:
                    continue
                for lead in campaign.get("leads", []):
                    if lead["id"] == lead_id:
                        return cid
        return None

    def add_leads(self, leads_list: List[Dict[str, Any]], campaign_id: Optional[str] = None) -> int:
        added_count = 0
        new_leads_to_add = []
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id not in self.state["campaigns"]:
                self.create_campaign_unsafe(f"Campaign {campaign_id}", campaign_id)
            
            campaign = self.state["campaigns"][campaign_id]
            
            for lead in leads_list:
                email = lead.get("email", "").strip().lower()
                if not email:
                    continue
                
                allow_duplicates = self.state["settings"].get("allow_duplicate_leads", True)
                if not allow_duplicates:
                    duplicate = False
                    for existing in campaign.get("leads", []):
                        if existing.get("email", "").strip().lower() == email:
                            duplicate = True
                            break
                    if duplicate:
                        continue
                
                new_lead = {
                    "id": str(uuid.uuid4()),
                    "company": lead.get("company", "Unknown Company").strip(),
                    "name": lead.get("name", "Unknown Contact").strip(),
                    "title": lead.get("title", "Contact").strip(),
                    "email": email,
                    "company_size": lead.get("company_size", "Unknown").strip(),
                    "industry": lead.get("industry", "Unknown").strip(),
                    "location": lead.get("location", "Unknown").strip(),
                    "branch": lead.get("branch", "Unknown").strip(),
                    "notes": lead.get("notes", "").strip(),
                    "icp_tags": lead.get("icp_tags", "").strip(),
                    "status": "Pending",
                    "score": 0,
                    "matched_segment": None,
                    "email_drafts": None,
                    "sequence_step": 0,
                    "last_sent_time": None,
                    "is_approved": False,
                    "custom_agent_instructions": lead.get("custom_agent_instructions", "").strip(),
                    "history": [{
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "Ingested",
                        "details": "Lead added to outreach queue"
                    }],
                    "replies": []
                }
                campaign["leads"].append(new_lead)
                new_leads_to_add.append(new_lead)
                added_count += 1
            
            if new_leads_to_add:
                with self._get_conn() as conn:
                    for lead in new_leads_to_add:
                        conn.execute("""
                            INSERT INTO leads (id, campaign_id, company, name, title, email, company_size, industry, location, branch, 
                                               notes, icp_tags, status, score, matched_segment, email_drafts, sequence_step, 
                                               last_sent_time, is_approved, custom_agent_instructions, history, replies, last_action_date, sender_account_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            lead["id"], campaign_id, lead["company"], lead["name"], lead["title"], lead["email"], 
                            lead["company_size"], lead["industry"], lead["location"], lead["branch"], lead["notes"], lead["icp_tags"], 
                            lead["status"], lead["score"], json.dumps(lead["matched_segment"]), json.dumps(lead["email_drafts"]), 
                            lead["sequence_step"], lead["last_sent_time"], int(lead["is_approved"]), lead["custom_agent_instructions"], 
                            json.dumps(lead["history"]), json.dumps(lead["replies"]), lead.get("last_action_date"), lead.get("sender_account_id", "primary")
                        ))
                    conn.commit()

            self.add_log_unsafe("INFO", f"Ingested {added_count} new leads.", None, campaign_id)
            self.update_campaign_stats_unsafe(campaign_id)
            
        return added_count

    def update_lead_status(self, lead_id: str, status: str, action: str, details: str, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.find_campaign_id_for_lead(lead_id)
            if not campaign_id:
                return
            
            campaign = self.state["campaigns"].get(campaign_id)
            if not campaign:
                return
            
            for lead in campaign.get("leads", []):
                if lead["id"] == lead_id:
                    lead["status"] = status
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": action,
                        "details": details
                    })
                    lead["last_action_date"] = datetime.datetime.now().isoformat()
                    self.add_log_unsafe("INFO", f"Lead {lead['name']} ({lead['company']}) status changed to {status}: {details}", lead_id, campaign_id)
                    
                    with self._get_conn() as conn:
                        conn.execute("""
                            UPDATE leads 
                            SET status = ?, history = ?, last_action_date = ? 
                            WHERE id = ?
                        """, (status, json.dumps(lead["history"]), lead["last_action_date"], lead_id))
                        conn.commit()
                    break
            self.update_campaign_stats_unsafe(campaign_id)

    def update_lead_sent_state(self, lead_id: str, status: str, last_sent_time: str, sequence_step: int, history: list, sender_account_id: Optional[str] = None, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.find_campaign_id_for_lead(lead_id)
            if not campaign_id:
                return
            
            campaign = self.state["campaigns"].get(campaign_id)
            if not campaign:
                return
            
            for lead in campaign.get("leads", []):
                if lead["id"] == lead_id:
                    lead["status"] = status
                    lead["last_sent_time"] = last_sent_time
                    lead["sequence_step"] = sequence_step
                    lead["history"] = history
                    lead["last_action_date"] = datetime.datetime.now().isoformat()
                    if sender_account_id:
                        lead["sender_account_id"] = sender_account_id
                    
                    with self._get_conn() as conn:
                        conn.execute("""
                            UPDATE leads 
                            SET status = ?, last_sent_time = ?, sequence_step = ?, history = ?, last_action_date = ?, sender_account_id = ?
                            WHERE id = ?
                        """, (status, last_sent_time, sequence_step, json.dumps(history), lead["last_action_date"], lead.get("sender_account_id", "primary"), lead_id))
                        conn.commit()
                    break
            self.update_campaign_stats_unsafe(campaign_id)

    def update_lead_drafts(self, lead_id: str, drafts: Dict[str, Any], matched_segment: Dict[str, Any], score: int, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.find_campaign_id_for_lead(lead_id)
            if not campaign_id:
                return
            
            campaign = self.state["campaigns"].get(campaign_id)
            if not campaign:
                return
            
            for lead in campaign.get("leads", []):
                if lead["id"] == lead_id:
                    lead["email_drafts"] = drafts
                    lead["matched_segment"] = matched_segment
                    lead["score"] = score
                    lead["is_approved"] = score >= 80
                    lead["status"] = "Ready" if lead["status"] in ["Pending", "Analyzing", "Matched", "Drafting"] else lead["status"]
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "AI Analysis Completed",
                        "details": f"Matched Offer: {matched_segment.get('go4db_offer')}. Email drafts generated (Score: {score})."
                    })
                    
                    with self._get_conn() as conn:
                        conn.execute("""
                            UPDATE leads 
                            SET email_drafts = ?, matched_segment = ?, score = ?, is_approved = ?, status = ?, history = ?
                            WHERE id = ?
                        """, (
                            json.dumps(drafts), json.dumps(matched_segment), score, int(lead["is_approved"]), lead["status"], 
                            json.dumps(lead["history"]), lead_id
                        ))
                        conn.commit()
                    break

    def update_lead_email_body(self, lead_id: str, email_type: str, subject: str, body: str, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.find_campaign_id_for_lead(lead_id)
            if not campaign_id:
                return
            
            campaign = self.state["campaigns"].get(campaign_id)
            if not campaign:
                return
            
            for lead in campaign.get("leads", []):
                if lead["id"] == lead_id:
                    if lead["email_drafts"] is None:
                        lead["email_drafts"] = {}
                    lead["email_drafts"][email_type] = {
                        "subject": subject,
                        "body": body
                    }
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": f"Draft Edited ({email_type})",
                        "details": f"Subject/body manually updated."
                    })
                    
                    with self._get_conn() as conn:
                        conn.execute("""
                            UPDATE leads 
                            SET email_drafts = ?, history = ?
                            WHERE id = ?
                        """, (json.dumps(lead["email_drafts"]), json.dumps(lead["history"]), lead_id))
                        conn.commit()
                    break

    def clear_all(self, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                campaign = self.state["campaigns"][campaign_id]
                self.preserve_historical_sends_before_clear_unsafe([campaign])
                campaign["leads"] = []
                campaign["logs"] = []
                campaign["campaign_status"] = {
                    "is_running": False,
                    "total_sent": 0,
                    "total_replies": 0,
                    "total_interested": 0,
                    "total_not_interested": 0,
                    "total_leads": 0,
                    "total_junk": 0
                }
                self.add_log_unsafe("INFO", "All lead data and logs cleared.", None, campaign_id)
                
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM leads WHERE campaign_id = ?", (campaign_id,))
                    conn.execute("DELETE FROM logs WHERE campaign_id = ?", (campaign_id,))
                    conn.execute("""
                        UPDATE campaigns 
                        SET campaign_status = ? 
                        WHERE id = ?
                    """, (json.dumps(campaign["campaign_status"]), campaign_id))
                    conn.commit()

    def get_campaign_status(self, campaign_id: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                self.update_campaign_stats_unsafe(campaign_id)
                return self.state["campaigns"][campaign_id]["campaign_status"]
            
            return {
                "is_running": False,
                "total_sent": 0,
                "total_replies": 0,
                "total_interested": 0,
                "total_not_interested": 0,
                "total_leads": 0
            }

    def set_campaign_running(self, running: bool, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                campaign = self.state["campaigns"][campaign_id]
                campaign["campaign_status"]["is_running"] = running
                status_str = "started" if running else "paused"
                self.add_log_unsafe("INFO", f"Campaign {status_str}.", None, campaign_id)
                
                with self._get_conn() as conn:
                    conn.execute("""
                        UPDATE campaigns 
                        SET campaign_status = ? 
                        WHERE id = ?
                    """, (json.dumps(campaign["campaign_status"]), campaign_id))
                    conn.commit()

    def update_campaign_stats_unsafe(self, campaign_id: str):
        if campaign_id not in self.state["campaigns"]:
            return
        
        campaign = self.state["campaigns"][campaign_id]
        leads = campaign.get("leads", [])
        total = len(leads)
        
        # Recalculate sent emails count by counting actual "sent" history items
        sent = sum(sum(1 for h in l.get("history", []) if "sent" in h.get("action", "").lower()) for l in leads)
        
        replies = sum(1 for l in leads if l["status"] in ["Replied", "Interested", "Not_Interested", "OOO", "Wrong_Contact", "Sample_Approval"])
        interested = sum(1 for l in leads if l["status"] == "Interested")
        not_interested = sum(1 for l in leads if l["status"] == "Not_Interested")
        junk = sum(1 for l in leads if l["status"] in ["Junk", "Bounced", "Wrong_Contact"])
        
        if "campaign_status" not in campaign:
            campaign["campaign_status"] = {}
            
        campaign["campaign_status"].update({
            "total_leads": total,
            "total_sent": sent,
            "total_replies": replies,
            "total_interested": interested,
            "total_not_interested": not_interested,
            "total_junk": junk
        })
        
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE campaigns 
                SET campaign_status = ? 
                WHERE id = ?
            """, (json.dumps(campaign["campaign_status"]), campaign_id))
            conn.commit()

    def get_campaigns(self) -> List[Dict[str, Any]]:
        with self.lock:
            result = []
            for cid, campaign in self.state.get("campaigns", {}).items():
                self.update_campaign_stats_unsafe(cid)
                leads = campaign.get("leads", [])
                stats = campaign.get("campaign_status", {})
                result.append({
                    "id": cid,
                    "name": campaign.get("name", "Unnamed Campaign"),
                    "created_at": campaign.get("created_at", datetime.datetime.now().isoformat()),
                    "size": len(leads),
                    "is_running": stats.get("is_running", False),
                    "total_sent": stats.get("total_sent", 0),
                    "total_replies": stats.get("total_replies", 0),
                    "total_interested": stats.get("total_interested", 0),
                    "total_not_interested": stats.get("total_not_interested", 0),
                    "total_junk": stats.get("total_junk", 0)
                })
            result.sort(key=lambda x: x["created_at"])
            return result

    def create_campaign_unsafe(self, name: str, campaign_id: Optional[str] = None, start_date: Optional[str] = None) -> str:
        if not campaign_id:
            campaign_id = str(uuid.uuid4())
        
        self.state["campaigns"][campaign_id] = {
            "id": campaign_id,
            "name": name,
            "created_at": datetime.datetime.now().isoformat(),
            "start_date": start_date,
            "leads": [],
            "logs": [],
            "campaign_status": {
                "is_running": False,
                "total_sent": 0,
                "total_replies": 0,
                "total_interested": 0,
                "total_not_interested": 0,
                "total_leads": 0,
                "total_junk": 0
            }
        }
        
        campaign = self.state["campaigns"][campaign_id]
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO campaigns (id, name, created_at, campaign_status, start_date)
                VALUES (?, ?, ?, ?, ?)
            """, (campaign_id, name, campaign["created_at"], json.dumps(campaign["campaign_status"]), start_date))
            conn.commit()

        self.add_log_unsafe("INFO", f"Campaign session '{name}' created.", None, campaign_id)
        return campaign_id

    def create_campaign(self, name: str, start_date: Optional[str] = None) -> str:
        with self.lock:
            campaign_id = self.create_campaign_unsafe(name, start_date=start_date)
        return campaign_id

    def set_campaign_start_date(self, campaign_id: str, start_date: Optional[str]):
        with self.lock:
            if campaign_id in self.state["campaigns"]:
                self.state["campaigns"][campaign_id]["start_date"] = start_date
                with self._get_conn() as conn:
                    conn.execute("UPDATE campaigns SET start_date = ? WHERE id = ?", (start_date, campaign_id))
                    conn.commit()

    def set_active_campaign(self, campaign_id: str):
        with self.lock:
            if campaign_id in self.state.get("campaigns", {}):
                self.state["active_campaign_id"] = campaign_id
                self.add_log_unsafe("INFO", f"Switched active campaign to '{self.state['campaigns'][campaign_id]['name']}'.", None, campaign_id)
                
                with self._get_conn() as conn:
                    conn.execute("""
                        INSERT INTO settings (key, value)
                        VALUES ('active_campaign_id', ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """, (json.dumps(campaign_id),))
                    conn.commit()

    def delete_campaign(self, campaign_id: str):
        with self.lock:
            if campaign_id in self.state.get("campaigns", {}):
                campaign = self.state["campaigns"][campaign_id]
                self.preserve_historical_sends_before_clear_unsafe([campaign])
                name = campaign.get("name", "Unnamed")
                del self.state["campaigns"][campaign_id]
                
                if self.state.get("active_campaign_id") == campaign_id:
                    if self.state["campaigns"]:
                        self.state["active_campaign_id"] = next(iter(self.state["campaigns"].keys()))
                    else:
                        self.create_campaign_unsafe("Default Session", "default")
                        self.state["active_campaign_id"] = "default"
                
                self.add_log_unsafe("INFO", f"Campaign session '{name}' deleted.", None, self.state["active_campaign_id"])
                
                with self._get_conn() as conn:
                    conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                    conn.execute("DELETE FROM leads WHERE campaign_id = ?", (campaign_id,))
                    conn.execute("DELETE FROM logs WHERE campaign_id = ?", (campaign_id,))
                    conn.execute("""
                        INSERT INTO settings (key, value)
                        VALUES ('active_campaign_id', ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """, (json.dumps(self.state["active_campaign_id"]),))
                    conn.commit()

    def add_simulated_reply(self, lead_id: str, reply_body: str, campaign_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        lead_to_update = None
        with self.lock:
            if not campaign_id:
                campaign_id = self.find_campaign_id_for_lead(lead_id)
            if not campaign_id:
                return None
            
            campaign = self.state["campaigns"].get(campaign_id)
            if not campaign:
                return None
            
            for lead in campaign.get("leads", []):
                if lead["id"] == lead_id:
                    reply_entry = {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "sender": lead["email"],
                        "body": reply_body
                    }
                    lead["replies"].append(reply_entry)
                    lead["status"] = "Replied"
                    lead["history"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "action": "Reply Received",
                        "details": f"Simulated message: \"{reply_body[:60]}...\""
                    })
                    lead_to_update = lead
                    self.add_log_unsafe("INFO", f"Simulated reply received from {lead['name']} ({lead['company']})", lead_id, campaign_id)
                    
                    with self._get_conn() as conn:
                        conn.execute("""
                            UPDATE leads 
                            SET replies = ?, status = ?, history = ?
                            WHERE id = ?
                        """, (json.dumps(lead["replies"]), lead["status"], json.dumps(lead["history"]), lead_id))
                        conn.commit()
                    break
            self.update_campaign_stats_unsafe(campaign_id)
        return lead_to_update

    def preserve_historical_sends_before_clear_unsafe(self, campaigns_list: list):
        import re
        settings = self.state.get("settings", {})
        historical_counts = settings.get("historical_send_counts", {})
        
        primary_email = (settings.get("sender_email") or settings.get("smtp_user") or "primary@example.com").lower().strip()
        
        for campaign in campaigns_list:
            leads = campaign.get("leads", [])
            for lead in leads:
                history = lead.get("history", [])
                for event in history:
                    action = event.get("action", "")
                    details = event.get("details", "")
                    
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
                            
                        historical_counts[sender_email] = historical_counts.get(sender_email, 0) + 1
                        
        settings["historical_send_counts"] = historical_counts
        
        # Save to database
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO settings (key, value)
                VALUES ('historical_send_counts', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (json.dumps(historical_counts),))
            conn.commit()

    def reset_warmup_stats(self):
        with self.lock:
            # 1. Clear historical_send_counts in memory and DB
            settings = self.state.get("settings", {})
            if "historical_send_counts" in settings:
                settings["historical_send_counts"] = {}
            with self._get_conn() as conn:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('historical_send_counts', '{}')")
                
                # 2. Reset all leads in all campaigns back to Pending
                conn.execute("""
                    UPDATE leads 
                    SET status = 'Pending', 
                        sequence_step = 0, 
                        last_sent_time = NULL, 
                        history = '[]', 
                        replies = '[]', 
                        last_action_date = NULL
                """)
                
                # 3. Reset campaign status in DB
                for c_id, campaign in self.state.get("campaigns", {}).items():
                    campaign["campaign_status"] = {
                        "is_running": False,
                        "total_sent": 0,
                        "total_replies": 0,
                        "total_interested": 0,
                        "total_not_interested": 0,
                        "total_leads": len(campaign.get("leads", [])),
                        "total_junk": 0
                    }
                    conn.execute("""
                        UPDATE campaigns 
                        SET campaign_status = ? 
                        WHERE id = ?
                    """, (json.dumps(campaign["campaign_status"]), c_id))
                    
                conn.commit()
                
            # 4. Reset campaigns in memory
            for c_id, campaign in self.state.get("campaigns", {}).items():
                for lead in campaign.get("leads", []):
                    lead["status"] = "Pending"
                    lead["sequence_step"] = 0
                    lead["last_sent_time"] = None
                    lead["history"] = []
                    lead["replies"] = []
                    lead["last_action_date"] = None
