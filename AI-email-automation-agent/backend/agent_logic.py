import os
import json
import re
from typing import Dict, Any, Tuple, Optional
import google.generativeai as genai

# Predefined Go4Database Offer Lists and descriptions
OFFERS = {
    "B2B Tech Buyers Contact List": {
        "description": "A verified database of 50M+ B2B decision makers, IT managers, CTOs, and tech buyers in the US, Europe, and Asia. Includes verified business emails and LinkedIn URLs.",
        "usecase": "To target IT leaders, software buyers, and technology decision makers directly without wasting ad spend.",
        "pain_points": ["Low outbound conversion rates", "Outdated business contacts", "Difficulty reaching technical decision makers"]
    },
    "US Real Estate Agent & Broker Database": {
        "description": "Comprehensive list of 2.1M+ licensed real estate agents, brokers, and realtors across the US, complete with verified business emails, LinkedIn profiles, and license statuses.",
        "usecase": "To market mortgage services, home improvement, property staging, or local marketing agencies to high-velocity agents.",
        "pain_points": ["Finding active local real estate leads", "High cost of Zillow/Redfin leads", "Reaching individual independent brokers"]
    },
    "Retail & E-commerce CXOs Directory": {
        "description": "Direct contact email database for founders, directors, and head-of-e-commerce professionals at 450,000+ online stores and physical retail brands globally.",
        "usecase": "To offer logistics, shipping solutions, design services, or e-commerce software to scaling brands.",
        "pain_points": ["Bouncing marketing emails to e-commerce brands", "Unable to pitch logistics/warehousing partners", "Gatekeepers blocking brand founders"]
    },
    "VC-backed Startups & Founders List": {
        "description": "Curated email directory of 120,000+ VC-funded and high-growth startup founders, C-level executives, and their early team members.",
        "usecase": "To sell dev services, agency packages, SaaS, or financial/legal consulting directly to funded founders looking to scale rapidly.",
        "pain_points": ["Missing key windows of startup funding cycles", "Inability to reach founders before they hire", "Slow B2B growth loops"]
    },
    "Active Job Seekers & Professionals Database": {
        "description": "Talent pool of 12M+ active job seekers, resumes, and candidate contacts matching high-demand industries like Tech, Finance, Engineering, and Healthcare. Includes verified emails and social coordinates.",
        "usecase": "To source talent directly, save on recruiting costs, and build a pipeline for staffing agency clients.",
        "pain_points": ["Extremely high LinkedIn Recruiter license costs", "Slow candidate sourcing", "Unresponsive candidates on public boards"]
    },
    "Local Healthcare & Medical Clinics Directory": {
        "description": "Directory of 650,000+ dentists, chiropractors, physical therapists, general practice clinics, and healthcare offices in the US and Canada. Includes verified emails.",
        "usecase": "To pitch medical supply vendors, specialized clinic software, billing systems, or local search marketing services.",
        "pain_points": ["Healthcare gatekeepers", "Finding verified contact channels", "Difficulty navigating clinic structures"]
    },
    "Custom B2B List Enrichment Service": {
        "description": "Go4Database's custom crawling and data appending service that updates name, business email addresses, and socials for any list of accounts or outdated contacts.",
        "usecase": "To clean and reactivate cold databases, reduce CRM bounce rates, and enrich missing lead details.",
        "pain_points": ["High bounce rates in email campaigns", "Outdated records in CRM", "Missing direct contact channels"]
    }
}

def analyze_and_draft_fallback(lead: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """
    Fallback rule-based lead analyzer and email compiler in case Gemini API key is missing or invalid.
    Uses the 5 approved strategies, enforces the < 60 words rule, avoids phone references, and cites 2-3% bounce rate.
    """
    industry = lead.get("industry", "").lower()
    title = lead.get("title", "").lower()
    company = lead.get("company", "your company")
    name_parts = (lead.get("name") or "there").split()
    first_name = name_parts[0] if name_parts else "there"
    notes = lead.get("notes", "").lower()
    icp_tags = lead.get("icp_tags", "").lower()

    # Rule matching to select strategy
    if any(x in industry or x in notes or x in icp_tags for x in ["saas", "software", "tech", "it", "developer"]):
        matched_offer = "B2B Tech Buyers Contact List"
        icp_fit = "B2B Software & IT Services Provider"
        branch = "Sales & Tech Partnerships"
        strategy = "competitor_comparison"
    elif any(x in industry or x in notes or x in icp_tags for x in ["real estate", "realtor", "property", "mortgage", "housing"]):
        matched_offer = "US Real Estate Agent & Broker Database"
        icp_fit = "Real Estate Services & Broker Marketing"
        branch = "Marketing & Partnerships"
        strategy = "case_study"
    elif any(x in industry or x in notes or x in icp_tags for x in ["retail", "ecommerce", "brand", "shop", "apparel", "store"]):
        matched_offer = "Retail & E-commerce CXOs Directory"
        icp_fit = "Direct-to-Consumer (D2C) & Retail"
        branch = "Growth & Marketing"
        strategy = "case_study"
    elif any(x in notes or x in icp_tags for x in ["hiring", "hired", "expansion", "expand", "new sector", "launch"]):
        matched_offer = "Custom B2B List Enrichment Service"
        icp_fit = "Expanding Enterprise Outreach"
        branch = "Founders Office / Business Development"
        strategy = "trigger_event"
    elif any(x in industry or x in notes or x in icp_tags for x in ["startup", "founder", "funded", "venture"]):
        matched_offer = "VC-backed Startups & Founders List"
        icp_fit = "High-Growth Startup"
        branch = "Founder's Office"
        strategy = "personalized_research"
    else:
        matched_offer = "Custom B2B List Enrichment Service"
        icp_fit = "B2B Professional Services & Consulting"
        branch = "Outbound Sales Development"
        strategy = "problem_solution"

    offer_info = OFFERS[matched_offer]
    pain_point = offer_info["pain_points"][0]
    usecase = offer_info["usecase"]

    # Calculate dynamic mock score (0-100)
    score = 50
    if any(x in title for x in ["ceo", "founder", "president", "chief"]):
        score += 25
    elif any(x in title for x in ["vp", "vice president", "director", "head"]):
        score += 20
    elif any(x in title for x in ["manager", "lead"]):
        score += 10
    else:
        score += 5
        
    comp_size_str = lead.get("company_size", "").strip()
    try:
        size_digits = re.findall(r'\d+', comp_size_str)
        if size_digits:
            size_val = int(size_digits[0])
            if 1 <= size_val <= 10:
                score += 5
            elif 11 <= size_val <= 50:
                score += 10
            elif 51 <= size_val <= 200:
                score += 15
            elif 201 <= size_val <= 500:
                score += 20
            else:
                score += 10
        else:
            if any(x in comp_size_str for x in ["1-10", "1-5", "6-10"]):
                score += 5
            elif "11-50" in comp_size_str:
                score += 10
            elif "51-200" in comp_size_str:
                score += 15
            elif "201-500" in comp_size_str:
                score += 20
            else:
                score += 5
    except Exception:
        score += 5

    if matched_offer != "Custom B2B List Enrichment Service":
        score += 10
    else:
        score += 5

    location = lead.get("location", "").lower()
    if any(x in location for x in ["united states", "us", "uk", "canada", "london", "york", "california", "texas"]):
        score += 5
    else:
        score += 2

    email = lead.get("email", "")
    variation = sum(ord(c) for c in email) % 10
    score += variation
    score = min(score, 100)

    matched_segment = {
        "icp_fit": icp_fit,
        "branch_target": branch,
        "pain_point": pain_point,
        "go4db_offer": matched_offer,
        "data_usecase": usecase
    }

    # Draft emails based on selected strategy
    drafts = {}
    
    if strategy == "problem_solution":
        drafts["initial_pitch"] = {
            "subject": f"Fix bounce rates for {company}?",
            "body": f"Hi {first_name},\n\nOutbound campaigns fail when contact data decays and emails bounce.\n\nAt go4database.com, we provide clean B2B email lists, keeping bounce rates under 2-3% to protect your sender score.\n\nWant to test a free sample of 15 contacts matching your ICP?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_1"] = {
            "subject": f"Re: Fix bounce rates for {company}?",
            "body": f"Hi {first_name},\n\nChecking back on this. Would a custom sample list of 15 target emails help you test our 2-3% bounce rate guarantee?\n\nLet me know if you'd like to check them out.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_2"] = {
            "subject": f"Re: Fix bounce rates for {company}?",
            "body": f"Hi {first_name},\n\nDid you have a chance to look at this? Deliverability is critical. I can pull a sample segment for {company} today.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_3"] = {
            "subject": f"Closing the loop / {company}",
            "body": f"Hi {first_name},\n\nSince I haven't heard back, I'll assume email deliverability isn't a priority for {company} right now.\n\nFeel free to reach out down the road if that changes.\n\nBest,\n[Sender Name]"
        }

    elif strategy == "competitor_comparison":
        drafts["initial_pitch"] = {
            "subject": f"flexible email list options for {company}",
            "body": f"Hi {first_name},\n\nMost B2B databases force you to buy expensive platform seats.\n\nAt go4database.com, we simply deliver verified, custom email lists matching your target criteria. You only pay for active contacts.\n\nCould I run a custom query for {company} this week?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_1"] = {
            "subject": f"Re: flexible email list options for {company}",
            "body": f"Hi {first_name},\n\nChecking back. If you are currently locked into seat-based licenses with other databases, we can export target verified lists directly to save your budget.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_2"] = {
            "subject": f"Re: flexible email list options for {company}",
            "body": f"Hi {first_name},\n\nJust checking in. If you have a target list of accounts you want to enrich, I can append active, verified emails today.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_3"] = {
            "subject": f"Closing the loop / {company}",
            "body": f"Hi {first_name},\n\nClosing the loop on this. Let me know if you ever want to compare our flexible pricing against seat-based alternatives.\n\nBest,\n[Sender Name]"
        }

    elif strategy == "trigger_event":
        target_industry = lead.get("industry") or "target"
        drafts["initial_pitch"] = {
            "subject": f"Sourcing {target_industry} contacts for {company}",
            "body": f"Hi {first_name},\n\nSaw {company} is expanding focus to target the {target_industry} sector.\n\nWe just refreshed our database and have verified emails of decision-makers in this space. Can I send you 15 sample leads to test?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_1"] = {
            "subject": f"Re: Sourcing {target_industry} contacts for {company}",
            "body": f"Hi {first_name},\n\nFollowing up. Sourcing verified emails is the fastest way to seed this new market and build outbound pipeline.\n\nLet me know if you want the 15 samples.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_2"] = {
            "subject": f"Re: Sourcing {target_industry} contacts for {company}",
            "body": f"Hi {first_name},\n\nDid you get a chance to check my note? I can customize the sample to match your exact size and location filters.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_3"] = {
            "subject": f"Closing the loop / {company}",
            "body": f"Hi {first_name},\n\nSince you are likely busy with the vertical expansion, I'll close the loop here. Feel free to ping if you need verified emails down the road.\n\nBest,\n[Sender Name]"
        }

    elif strategy == "case_study":
        drafts["initial_pitch"] = {
            "subject": f"Outbound results for {company}",
            "body": f"Hi {first_name},\n\nWe helped a similar {icp_fit} scale outbound bookings by 3x and keep bounce rates under 2.5% using our verified tech buyer emails.\n\nWe have a matching segment of verified decision-makers for {company}.\n\nCan I send you the brief case study and a small sample list?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_1"] = {
            "subject": f"Re: Outbound results for {company}",
            "body": f"Hi {first_name},\n\nFollowing up. I'd love to share the exact outbound list strategy they used to achieve these results. Would you like a quick look?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_2"] = {
            "subject": f"Re: Outbound results for {company}",
            "body": f"Hi {first_name},\n\nJust checking in. I can also include a sample of 15 contacts matching your target profile to check details.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_3"] = {
            "subject": f"Closing the loop / {company}",
            "body": f"Hi {first_name},\n\nAssuming outbound efficiency isn't a priority for {company} right now. I'll close the loop here. Thanks!\n\nBest,\n[Sender Name]"
        }

    else:  # personalized_research
        lead_count = "1,450" if score > 75 else "320"
        title_tag = lead.get("title") or "decision-maker"
        drafts["initial_pitch"] = {
            "subject": f"{title_tag} lists for {company}",
            "body": f"Hi {first_name},\n\nI ran a quick query in our database for {company}'s target buyers.\n\nWe have {lead_count} verified contacts (business emails and LinkedIn profiles) matching your exact ICP. Would you like a free sample of 10 leads to check their accuracy?\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_1"] = {
            "subject": f"Re: {title_tag} lists for {company}",
            "body": f"Hi {first_name},\n\nFollowing up on this count. I can export the verified emails for these {lead_count} decision-makers directly. Let me know if you'd like a sample first.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_2"] = {
            "subject": f"Re: {title_tag} lists for {company}",
            "body": f"Hi {first_name},\n\nDid you see the custom count I pulled? Would love to share a small batch to prove our database freshness.\n\nBest,\n[Sender Name]"
        }
        drafts["follow_up_3"] = {
            "subject": f"Closing the loop / {company}",
            "body": f"Hi {first_name},\n\nClosing the loop on this custom count. If you ever need fresh target emails for {company}, we are here.\n\nBest,\n[Sender Name]"
        }

    return matched_segment, drafts, score


def analyze_and_draft(lead: Dict[str, Any], api_key: str = "") -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """
    Analyzes lead profile and generates custom Go4Database offer + email sequences using Gemini.
    Falls back to rule-based generation if API call fails or API key is not configured.
    """
    if not api_key:
        return analyze_and_draft_fallback(lead)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        offers_str = json.dumps(OFFERS, indent=2)

        prompt = f"""
You are an expert AI sales outreach agent working for "Go4Database" (go4database.com). 
Go4Database is a B2B lead generation database provider with 350M+ records globally, offering business emails and LinkedIn profiles.

Your task is to:
1. Define a highly specific ICP (Ideal Customer Profile) fit for this prospect's company.
2. Select the single best Go4Database offer/list that helps them.
3. Select ONE of the 5 approved strategies below to guide the entire outreach sequence:
   - "problem_solution": Focuses on fixing email bounce rates (MUST cite a "2-3% bounce rate guarantee" with Go4Database).
   - "personalized_research": Custom lead count segment matching their ICP, or a mock segment of 3 sample target leads pasted directly in the body.
   - "trigger_event": Connects to a vertical expansion, launch, or hiring signal in a new sector.
   - "competitor_comparison": Highlights Go4Database's flexible pay-per-lead email list export against expensive seat-based platform limits like ZoomInfo/Apollo/Lusha.
   - "case_study": Cites metric-driven success from a similar company (e.g. scaling bookings by 3x, or cutting research time by 80%).
4. Generate a highly personalized 4-step email sequence matching that single chosen strategy.

Prospect Profile:
- Name: {lead.get('name')}
- Title/Position: {lead.get('title')}
- Company: {lead.get('company')}
- Industry: {lead.get('industry')}
- Company Size: {lead.get('company_size')}
- Location/Branch: {lead.get('location')} / {lead.get('branch')}
- Notes: {lead.get('notes')}
- ICP Tags: {lead.get('icp_tags')}

Available Go4Database Offers:
{offers_str}

========================
EMAIL PERSONALIZATION & STRATEGY RULES:
========================
- NO PHONE NUMBERS: Go4Database does NOT provide phone numbers or direct dials. Do not mention direct dials, phone numbers, or phone calls in any subject or body.
- SEQUENCE STRATEGY CONSISTENCY: The initial pitch and all follow-ups (Follow-up 1, Follow-up 2, Follow-up 3) MUST use the exact same strategy selected.
- NO BRACKETS OR GENERIC PLACEHOLDERS: Except for "[Sender Name]" at the end of the email, NEVER use generic brackets or placeholders like "[Founder Name]", "[Title]", "[Email]", "[Prospect Name]", "[Company]", or similar in the subject or body.
- FOR PERSONALIZED RESEARCH SAMPLE LEADS: If you generate sample leads in the email body, you MUST invent 3 highly realistic, relevant names, B2B titles, and email addresses matching the target company's buyer persona (e.g., "Sarah Jenkins, CTO at Veloce Security, sarah@veloce.io") instead of leaving placeholders.
- SHORT & CRISP: The initial pitch MUST be extremely short, conversational, and under 60 words.
- Follow-ups must also be very short, direct, and conversational (under 60 words), sent on Day 3, Day 5, and Day 7 respectively.
- Use natural contractions ("we've", "it's", "you'll", "don't"). Avoid robotic corporate greetings.

Please generate the following in a JSON structure:
1. "matched_segment":
   - "icp_fit": Highly personalized, specific description of the prospect's business model/ICP.
   - "branch_target": Specific department (e.g. Sales Partnerships, Growth Marketing, Founder's Office).
   - "pain_point": A major lead generation, data decay, or sales pipeline challenge they experience.
   - "go4db_offer": Name of the EXACT matching Go4Database list/service from the list above.
   - "data_usecase": A highly specific use case explaining how the prospect can use the Go4Database list to grow their revenue.
2. "score": Outreach fit score (0 to 100) based on title, size, and relevance.
3. "email_drafts":
   - "initial_pitch": Subject and Body (under 60 words, matches chosen strategy, no phone references, ends with soft CTA).
   - "follow_up_1": Subject and Body (nudge sent 2 days after, on Day 3).
   - "follow_up_2": Subject and Body (check-in sent 2 days after follow_up_1, on Day 5).
   - "follow_up_3": Subject and Body (final close breakup sent 2 days after follow_up_2, on Day 7).

Use [Sender Name] as a placeholder for the sender in the drafts.
Your response must be ONLY valid JSON, with no other text, markdown blocks, preambles, or postscripts.
JSON Structure:
{{
  "matched_segment": {{
     "icp_fit": "string",
     "branch_target": "string",
     "pain_point": "string",
     "go4db_offer": "string",
     "data_usecase": "string"
  }},
  "score": number,
  "email_drafts": {{
     "initial_pitch": {{ "subject": "string", "body": "string" }},
     "follow_up_1": {{ "subject": "string", "body": "string" }},
     "follow_up_2": {{ "subject": "string", "body": "string" }},
     "follow_up_3": {{ "subject": "string", "body": "string" }}
  }}
}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean potential markdown wrapping
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return data["matched_segment"], data["email_drafts"], int(data.get("score", 70))
    except Exception as e:
        print(f"Gemini API error: {e}. Falling back to rule-based engine.")
        return analyze_and_draft_fallback(lead)


def strip_reply_history(body: str) -> str:
    if not body:
        return ""
    
    # Common markers that separate the reply from the quoted thread
    markers = [
        r"(?i)^\s*On\s+.*,\s+.*wrote\s*:\s*$", # On Tue, Jun 9, 2026 at 1:57 PM Anna <...> wrote:
        r"(?i)^\s*On\s+.*wrote\s*:\s*$",      # On Tue, Jun 9, 2026 Anna wrote:
        r"(?i)^-----Original Message-----",
        r"(?i)^From:",
        r"(?i)^Sent:",
        r"(?i)^To:",
        r"(?i)^Subject:",
    ]
    
    lines = body.splitlines()
    reply_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        # Check if line matches any quoted marker
        is_marker = False
        for marker in markers:
            if re.search(marker, stripped_line):
                is_marker = True
                break
        if is_marker:
            break
            
        # Check if line starts with > (quoted line)
        if stripped_line.startswith(">"):
            continue
            
        reply_lines.append(line)
        
    return "\n".join(reply_lines).strip()

def qualify_and_draft_reply_fallback(lead: Dict[str, Any], reply_body: str) -> Dict[str, Any]:
    cleaned_reply = strip_reply_history(reply_body)
    body_lower = cleaned_reply.lower()
    body_norm = body_lower.replace("'", "").replace("’", "").replace("`", "")
    
    # Check Out of Office
    ooo_keywords = ["out of office", "vacation", "annual leave", "ooo", "snooze", "until i return", "returning on", "away from my"]
    if any(x in body_norm for x in ooo_keywords):
        return {
            "lead_stage": "OOO",
            "qualification_score": 0,
            "pain_points": [],
            "buying_intent": "Low",
            "next_action": "Snooze automated campaigns.",
            "response_to_send": ""
        }
    
    # Check Wrong Contact
    wrong_contact_keywords = ["not the right person", "wrong contact", "wrong person", "try contacting", "not in charge", "forwarded to", "not the person"]
    if any(x in body_norm for x in wrong_contact_keywords):
        return {
            "lead_stage": "Disqualified",
            "qualification_score": 10,
            "pain_points": [],
            "buying_intent": "Low",
            "next_action": "Remove contact and search for correct decision maker.",
            "response_to_send": "Understood. I will update our records. If you can point me to the right person, that would be great. Thanks!"
        }

    # Check Not Interested
    not_interested_keywords = [
        "not interested", "not intrested", "no interest", "no intrest",
        "unsubscribe", "remove", "stop", "dont send", "dont email", 
        "dont mail", "stop mailing", "stop emailing", "stop sending", 
        "please dont", "please do not", "no thanks", "not looking",
        "dont write", "no further", "dont contact", "do not contact"
    ]
    if any(x in body_norm for x in not_interested_keywords):
        return {
            "lead_stage": "Disqualified",
            "qualification_score": 0,
            "pain_points": [],
            "buying_intent": "Low",
            "next_action": "Opt-out / Remove from list.",
            "response_to_send": "Understood. I have removed you from our outbound list."
        }

    # Check Sample Approval
    sample_keywords = ["sample", "test list", "demo sample", "data test", "contacts sample", "list sample", "sample of"]
    if any(x in body_norm for x in sample_keywords):
        return {
            "lead_stage": "Sample Approval",
            "qualification_score": 85,
            "pain_points": ["Wants database sample"],
            "buying_intent": "High",
            "next_action": "Compile sample list and seek approval.",
            "response_to_send": "Hi,\n\nI'd be happy to prepare a sample list of 20 leads matching your target criteria. Let me verify the details and I'll send it over for your approval."
        }

    # Check Escalation / Handoff
    escalate_keywords = ["pricing", "cost", "proposal", "contract", "quote", "legal", "compliance", "integration"]
    if any(x in body_norm for x in escalate_keywords):
        return {
            "lead_stage": "SQL",
            "qualification_score": 90,
            "pain_points": ["Requires custom details"],
            "buying_intent": "High",
            "next_action": "Escalate to human sales: requested pricing or technical details.",
            "response_to_send": "Hi,\n\nThanks for reaching out. I'll have a sales manager follow up shortly with pricing and proposal details. Would next week work for a brief call?"
        }

    # Check SQL
    sql_keywords = ["call", "zoom", "meeting", "schedule", "demo", "yes", "sure", "sounds good", "please send"]
    if any(x in body_norm for x in sql_keywords):
        return {
            "lead_stage": "SQL",
            "qualification_score": 80,
            "pain_points": ["Looking for demo/call"],
            "buying_intent": "High",
            "next_action": "Schedule sales call / book meeting.",
            "response_to_send": "Hi,\n\nI'd be happy to arrange a short call to explore how we can help. Would next week work for you?"
        }

    # Check MQL
    interested_keywords = ["interested", "intrested", "details", "info", "information"]
    if any(x in body_norm for x in interested_keywords):
        return {
            "lead_stage": "MQL",
            "qualification_score": 60,
            "pain_points": ["Evaluating options"],
            "buying_intent": "Medium",
            "next_action": "Send educational information and build trust.",
            "response_to_send": "Hi,\n\nThanks for the interest! I'd be happy to send over details. What challenges are you currently facing with your target outreach?"
        }

    # Default to MQL
    return {
        "lead_stage": "MQL",
        "qualification_score": 50,
        "pain_points": ["Inbound inquiry"],
        "buying_intent": "Medium",
        "next_action": "Nurture lead.",
        "response_to_send": "Hi,\n\nThanks for reaching out. What caught your attention about our solution?"
    }


DEFAULT_SDR_PERSONA = """You are an expert Sales Development Representative (SDR) for our company, Go4Database (a B2B lead generation database provider with 350M+ records).
Your primary goal is to qualify prospects and move them through the sales pipeline from MQL to SQL.
You should communicate naturally, professionally, and conversationally. Never sound robotic or pushy.

========================
YOUR OBJECTIVES
========================
1. Understand the prospect's situation.
2. Identify their pain points.
3. Determine if they fit our Ideal Customer Profile (ICP).
4. Qualify them based on:
   - Need
   - Company fit
   - Budget (if relevant)
   - Authority
   - Timeline

5. Categorize leads into:
MQL (Marketing Qualified Lead):
- Interested but not ready.
- Needs more information.
- Exploring options.
- No immediate buying intent.

SQL (Sales Qualified Lead):
- Has a clear need.
- Shows buying intent.
- Wants pricing/demo/proposal.
- Interested in discussing implementation.
- Ready for a sales call.

Sample Approval:
- Prospect requested a target database sample matching specific ICP criteria.
- Needs custom records to test quality before booking call / proceeding.

(If they are asking to unsubscribe, are not interested, are wrong contact, or this is an OOO auto-response, classify the lead_stage as "Disqualified" or "OOO" respectively, and keep qualification_score low).

========================
CONVERSATION RULES
========================
- Do not ask more than one or two questions at a time.
- Focus on understanding:
   - Current workflow
   - Existing tools
   - Challenges
   - Team size
   - Decision-making process
- Keep responses concise.
- Always acknowledge the prospect's previous message before asking the next question.
- Never make false claims.
- Never pressure the prospect.

========================
QUALIFICATION FLOW
========================
- Step 1: Understand why they responded (What caught attention? Challenges?).
- Step 2: Explore pain points (How handling current process? Biggest challenge?).
- Step 3: Assess urgency (Actively looking to solve? Evaluating solutions now?).
- Step 4: Determine buying readiness (Who is involved in decisions? Timeline?).

========================
MQL ACTIONS
========================
If the lead is MQL:
- Share relevant value propositions.
- Offer educational resources (if requested).
- Address early objections.
- Do not push for a meeting yet.

========================
SQL ACTIONS
========================
If the lead is SQL:
- Focus on scheduling a meeting.
- Share case studies / success stories.
- Address specific pricing or proposal questions.
- Hand off to human sales representative."""

DEFAULT_SDR_TRAINING = {
    "customer_to_mql": "Understand the prospect's situation, their role, and company fit. Communicate naturally, professionally, and conversationally. Answer introductory questions, explore initial interest, and offer to prepare a custom sample list.",
    "mql_to_sql": "Explore pain points (e.g. low conversions, outdated contacts, gatekeepers) and current outbound tools/workflow. Qualify on need and authority. Recommend a sales discussion / book a meeting.",
    "sql_to_sample_approval": "Identify if the prospect asks for custom data samples (e.g. 'send me a sample list'). Ask clarifying questions about their target filters (industries, location, size) to compile the sample. Guide them to sample approval."
}

def qualify_and_draft_reply(lead: Dict[str, Any], reply_body: str, api_key: str = "", sdr_training: Optional[Dict[str, str]] = None, sdr_persona: Optional[str] = None) -> Dict[str, Any]:
    """
    SDR agent logic that qualifies the lead reply and drafts the next response.
    Returns:
    {
      "lead_stage": "MQL" | "SQL" | "Sample Approval" | "Disqualified" | "OOO",
      "qualification_score": 0-100,
      "pain_points": ["string"],
      "buying_intent": "Low" | "Medium" | "High",
      "next_action": "string",
      "response_to_send": "string"
    }
    """
    if not api_key:
        return qualify_and_draft_reply_fallback(lead, reply_body)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        sdr_rules = sdr_training if sdr_training else DEFAULT_SDR_TRAINING
        customer_to_mql = sdr_rules.get("customer_to_mql", "")
        mql_to_sql = sdr_rules.get("mql_to_sql", "")
        sql_to_sample_approval = sdr_rules.get("sql_to_sample_approval", "")
        
        lead_custom_instructions = lead.get("custom_agent_instructions", "").strip()
        custom_instructions_str = ""
        if lead_custom_instructions:
            custom_instructions_str = f"""
========================
HYPER-PERSONALIZED INSTRUCTIONS FOR THIS PROSPECT
========================
You MUST strictly follow these specific guidelines for this prospect's conversation:
{lead_custom_instructions}
"""

        history_str = ""
        for hist in lead.get("history", []):
            if "Email Sent" in hist.get("action", "") or "Follow-up" in hist.get("action", ""):
                history_str += f"- {hist.get('action')}: {hist.get('details')}\n"

        persona_str = sdr_persona if sdr_persona else DEFAULT_SDR_PERSONA

        prompt = f"""
{persona_str}

========================
SDR STAGE TRANSITION TRAINING RULES
========================
Use these specific transition instructions to qualify the lead and draft response copy:
- Customer to MQL: {customer_to_mql}
- MQL to SQL: {mql_to_sql}
- SQL to Sample Approval: {sql_to_sample_approval}
{custom_instructions_str}

========================
HANDOFF / ESCALATION RULES
========================
Immediately escalate to human sales if:
- Prospect requests pricing.
- Prospect requests proposal.
- Prospect asks legal/compliance questions.
- Prospect asks technical implementation questions beyond available knowledge.
- Prospect requests contract information.
If escalation is triggered, next_action should start with "Escalate to human sales: [reason]" and the response should let them know we'll have a team member follow up with those details.

========================
CONTEXT
========================
Prospect Info:
- Name: {lead.get('name')}
- Title: {lead.get('title')}
- Company: {lead.get('company')}
- Industry: {lead.get('industry')}
- Matched Go4Database Offer: {lead.get('matched_segment', {}).get('go4db_offer', 'B2B Lists')}

Outbound Conversation History:
{history_str}

Incoming Prospect Reply:
\"\"\"
{reply_body}
\"\"\"

========================
OUTPUT FORMAT
========================
Your response must be ONLY a valid JSON object. No markdown wrapping (like ```json), no other text, preambles, or postscripts.
JSON Structure:
{{
  "lead_stage": "MQL" | "SQL" | "Sample Approval" | "Disqualified" | "OOO",
  "qualification_score": number,
  "pain_points": ["string"],
  "buying_intent": "Low" | "Medium" | "High",
  "next_action": "string",
  "response_to_send": "string"
}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        return json.loads(text)
    except Exception as e:
        print(f"Gemini SDR qualification failed: {e}. Falling back to rules engine.")
        return qualify_and_draft_reply_fallback(lead, reply_body)


def classify_reply(lead: Dict[str, Any], reply_body: str, api_key: str = "") -> Tuple[str, str]:
    res = qualify_and_draft_reply(lead, reply_body, api_key)
    stage = res.get("lead_stage", "MQL")
    if stage == "SQL":
        return "Interested", res.get("next_action", "")
    elif stage == "Sample Approval":
        return "Sample_Approval", res.get("next_action", "")
    elif stage == "MQL":
        return "Needs_Follow_Up_Pending", res.get("next_action", "")
    elif stage == "Disqualified":
        return "Not_Interested", res.get("next_action", "")
    elif stage == "OOO":
        return "OOO", "Out of office"
    return "Needs_Follow_Up_Pending", res.get("next_action", "")


def generate_custom_followup(lead: Dict[str, Any], reply_body: str, category: str, api_key: str = "") -> str:
    res = qualify_and_draft_reply(lead, reply_body, api_key)
    return res.get("response_to_send", "")
