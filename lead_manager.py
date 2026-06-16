import os
import json
import uuid
import datetime
import threading
from typing import List, Dict, Any, Optional

STATE_FILE = "campaign_state.json"

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
                "min_delay": 5,  # seconds (for demo/speed)
                "max_delay": 15, # seconds (for demo/speed)
                "auto_followup_delay_days": 24,
                "automation_mode": False,  # False = requires manual approval before sending
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

    def load_state(self):
        with self.lock:
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, "r") as f:
                        saved_state = json.load(f)
                        
                        # Load settings if present (shared globally)
                        if "settings" in saved_state:
                            self.state["settings"].update(saved_state["settings"])
                            if "sdr_training" not in saved_state["settings"]:
                                self.state["settings"]["sdr_training"] = {
                                    "customer_to_mql": "Understand the prospect's situation, their role, and company fit. Communicate naturally, professionally, and conversationally. Answer introductory questions, explore initial interest, and offer to prepare a custom sample list.",
                                    "mql_to_sql": "Explore pain points (e.g. low conversions, outdated contacts, gatekeepers) and current outbound tools/workflow. Qualify on need and authority. Recommend a sales discussion / book a meeting.",
                                    "sql_to_sample_approval": "Identify if the prospect asks for custom data samples (e.g. 'send me a sample list'). Ask clarifying questions about their target filters (industries, location, size) to compile the sample. Guide them to sample approval."
                                }
                            if "sdr_persona" not in saved_state["settings"]:
                                self.state["settings"]["sdr_persona"] = DEFAULT_SDR_PERSONA
                            if not self.state["settings"].get("gemini_api_key") and os.getenv("GEMINI_API_KEY"):
                                self.state["settings"]["gemini_api_key"] = os.getenv("GEMINI_API_KEY")
                        
                        # Load users list
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
                        else:
                            self.state["users"] = [
                                {
                                    "id": "admin_user",
                                    "name": "Admin User",
                                    "email": "admin@admin.com",
                                    "password": "admin123",
                                    "role": "Admin"
                                }
                            ]

                        # Perform backward compatibility migration
                        # If "leads" exists in the saved state at the root level, it is the old schema
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
                            
                            # Migrate done - now update global logs and stats safely
                            self.add_log_unsafe("INFO", "Migrated legacy campaign state to multi-session schema.", None, "default")
                        else:
                            # If it is the new schema
                            if "active_campaign_id" in saved_state:
                                self.state["active_campaign_id"] = saved_state["active_campaign_id"]
                            if "campaigns" in saved_state:
                                self.state["campaigns"] = saved_state["campaigns"]
                                
                                # Make sure all campaigns have a valid campaign_status structure
                                for cid, campaign in self.state["campaigns"].items():
                                    if "campaign_status" not in campaign:
                                        campaign["campaign_status"] = {
                                            "is_running": False,
                                            "total_sent": 0,
                                            "total_replies": 0,
                                            "total_interested": 0,
                                            "total_not_interested": 0,
                                            "total_leads": 0
                                        }
                            
                            # Fallback if active_campaign_id is invalid or campaigns is empty
                            if not self.state["campaigns"]:
                                self.state["campaigns"] = {
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
                            if self.state["active_campaign_id"] not in self.state["campaigns"]:
                                self.state["active_campaign_id"] = next(iter(self.state["campaigns"].keys()))
                except Exception as e:
                    print(f"Failed to load campaign state: {str(e)}")

    def save_state(self):
        with self.lock:
            try:
                with open(STATE_FILE, "w") as f:
                    json.dump(self.state, f, indent=4)
            except Exception as e:
                print(f"Error saving state: {e}")

    def add_log_unsafe(self, level: str, message: str, lead_id: Optional[str] = None, campaign_id: Optional[str] = None):
        if not campaign_id:
            campaign_id = self.state.get("active_campaign_id", "default")
        
        # Ensure target campaign exists, if not, write to default or active if default doesn't exist
        if campaign_id not in self.state["campaigns"]:
            if self.state["campaigns"]:
                campaign_id = next(iter(self.state["campaigns"].keys()))
            else:
                print(f"[{level}] {message}")
                return
        
        campaign = self.state["campaigns"][campaign_id]
        if "logs" not in campaign:
            campaign["logs"] = []
            
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "level": level,
            "message": message,
            "lead_id": lead_id
        }
        campaign["logs"].append(log_entry)
        if len(campaign["logs"]) > 1000:
            campaign["logs"] = campaign["logs"][-1000:]

    def add_log(self, level: str, message: str, lead_id: Optional[str] = None, campaign_id: Optional[str] = None):
        with self.lock:
            self.add_log_unsafe(level, message, lead_id, campaign_id)
        self.save_state()

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
        self.save_state()

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
                added_count += 1
            
            self.add_log_unsafe("INFO", f"Ingested {added_count} new leads.", None, campaign_id)
            self.update_campaign_stats_unsafe(campaign_id)
        self.save_state()
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
                    break
            self.update_campaign_stats_unsafe(campaign_id)
        self.save_state()

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
                    break
        self.save_state()

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
                    break
        self.save_state()

    def clear_all(self, campaign_id: Optional[str] = None):
        with self.lock:
            if not campaign_id:
                campaign_id = self.state.get("active_campaign_id", "default")
            
            if campaign_id in self.state["campaigns"]:
                campaign = self.state["campaigns"][campaign_id]
                campaign["leads"] = []
                campaign["logs"] = []
                campaign["campaign_status"] = {
                    "is_running": False,
                    "total_sent": 0,
                    "total_replies": 0,
                    "total_interested": 0,
                    "total_not_interested": 0,
                    "total_leads": 0
                }
                self.add_log_unsafe("INFO", "All lead data and logs cleared.", None, campaign_id)
        self.save_state()

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
        self.save_state()

    def update_campaign_stats_unsafe(self, campaign_id: str):
        if campaign_id not in self.state["campaigns"]:
            return
        
        campaign = self.state["campaigns"][campaign_id]
        leads = campaign.get("leads", [])
        total = len(leads)
        sent = sum(l.get("sequence_step", 0) for l in leads)
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

    def create_campaign_unsafe(self, name: str, campaign_id: Optional[str] = None) -> str:
        if not campaign_id:
            campaign_id = str(uuid.uuid4())
        
        self.state["campaigns"][campaign_id] = {
            "id": campaign_id,
            "name": name,
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
        self.add_log_unsafe("INFO", f"Campaign session '{name}' created.", None, campaign_id)
        return campaign_id

    def create_campaign(self, name: str) -> str:
        with self.lock:
            campaign_id = self.create_campaign_unsafe(name)
        self.save_state()
        return campaign_id

    def set_active_campaign(self, campaign_id: str):
        with self.lock:
            if campaign_id in self.state.get("campaigns", {}):
                self.state["active_campaign_id"] = campaign_id
                self.add_log_unsafe("INFO", f"Switched active campaign to '{self.state['campaigns'][campaign_id]['name']}'.", None, campaign_id)
        self.save_state()

    def delete_campaign(self, campaign_id: str):
        with self.lock:
            if campaign_id in self.state.get("campaigns", {}):
                name = self.state["campaigns"][campaign_id].get("name", "Unnamed")
                del self.state["campaigns"][campaign_id]
                
                if self.state.get("active_campaign_id") == campaign_id:
                    if self.state["campaigns"]:
                        self.state["active_campaign_id"] = next(iter(self.state["campaigns"].keys()))
                    else:
                        self.create_campaign_unsafe("Default Session", "default")
                        self.state["active_campaign_id"] = "default"
                
                self.add_log_unsafe("INFO", f"Campaign session '{name}' deleted.", None, self.state["active_campaign_id"])
        self.save_state()

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
                    break
            self.update_campaign_stats_unsafe(campaign_id)
        self.save_state()
        return lead_to_update
