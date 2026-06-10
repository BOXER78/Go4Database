import os
import json
import re
from typing import Dict, Any, Tuple
import google.generativeai as genai

# Predefined Go4Database Offer Lists and descriptions
OFFERS = {
    "B2B Tech Buyers Contact List": {
        "description": "A verified database of 50M+ B2B decision makers, IT managers, CTOs, and tech buyers in the US, Europe, and Asia. Includes verified emails, direct dials, and LinkedIn URLs.",
        "usecase": "To target IT leaders, software buyers, and technology decision makers directly without wasting ad spend.",
        "pain_points": ["Low outbound conversion rates", "Outdated business contacts", "Difficulty reaching technical decision makers"]
    },
    "US Real Estate Agent & Broker Database": {
        "description": "Comprehensive list of 2.1M+ licensed real estate agents, brokers, and realtors across the US, complete with office emails, cell phone numbers, and license statuses.",
        "usecase": "To market mortgage services, home improvement, property staging, or local marketing agencies to high-velocity agents.",
        "pain_points": ["Finding active local real estate leads", "High cost of Zillow/Redfin leads", "Reaching individual independent brokers"]
    },
    "Retail & E-commerce CXOs Directory": {
        "description": "Direct contact database for founders, directors, and head-of-e-commerce professionals at 450,000+ online stores and physical retail brands globally.",
        "usecase": "To offer logistics, shipping solutions, design services, or e-commerce software to scaling brands.",
        "pain_points": ["Bouncing marketing emails to e-commerce brands", "Unable to pitch logistics/warehousing partners", "Gatekeepers blocking brand founders"]
    },
    "VC-backed Startups & Founders List": {
        "description": "Curated directory of 120,000+ VC-funded and high-growth startup founders, C-level executives, and their early team members.",
        "usecase": "To sell dev services, agency packages, SaaS, or financial/legal consulting directly to funded founders looking to scale rapidly.",
        "pain_points": ["Missing key windows of startup funding cycles", "Inability to reach founders before they hire", "Slow B2B growth loops"]
    },
    "Active Job Seekers & Professionals Database": {
        "description": "Talent pool of 12M+ active job seekers, resumes, and candidate contacts matching high-demand industries like Tech, Finance, Engineering, and Healthcare.",
        "usecase": "To source talent directly, save on recruiting costs, and build a pipeline for staffing agency clients.",
        "pain_points": ["Extremely high LinkedIn Recruiter license costs", "Slow candidate sourcing", "Unresponsive candidates on public boards"]
    },
    "Local Healthcare & Medical Clinics Directory": {
        "description": "Directory of 650,000+ dentists, chiropractors, physical therapists, general practice clinics, and healthcare offices in the US and Canada.",
        "usecase": "To pitch medical supply vendors, specialized clinic software, billing systems, or local search marketing services.",
        "pain_points": ["Healthcare gatekeepers", "Finding verified direct office lines", "Difficulty navigating clinic structures"]
    },
    "Custom B2B List Enrichment Service": {
        "description": "Go4Database's custom crawling and data appending service that updates name, direct dials, email addresses, and socials for any list of accounts or outdated contacts.",
        "usecase": "To clean and reactivate cold databases, reduce CRM bounce rates, and enrich missing lead details.",
        "pain_points": ["High bounce rates in email campaigns", "Outdated records in CRM", "Missing direct contact channels"]
    }
}

def analyze_and_draft_fallback(lead: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    """
    Fallback rule-based lead analyzer and email compiler in case Gemini API key is missing or invalid.
    """
    industry = lead.get("industry", "").lower()
    title = lead.get("title", "").lower()
    company = lead.get("company", "your company")
    name_parts = (lead.get("name") or "there").split()
    first_name = name_parts[0] if name_parts else "there"
    notes = lead.get("notes", "").lower()

    # Rule matching
    if any(x in industry or x in notes for x in ["saas", "software", "tech", "it", "developer"]):
        matched_offer = "B2B Tech Buyers Contact List"
        icp_fit = "B2B Software & IT Services Provider"
        branch = "Sales & Tech Partnerships"
    elif any(x in industry or x in notes for x in ["real estate", "realtor", "property", "mortgage", "housing"]):
        matched_offer = "US Real Estate Agent & Broker Database"
        icp_fit = "Real Estate Services & Broker Marketing"
        branch = "Marketing & Partnerships"
    elif any(x in industry or x in notes for x in ["retail", "ecommerce", "brand", "shop", "apparel", "store"]):
        matched_offer = "Retail & E-commerce CXOs Directory"
        icp_fit = "Direct-to-Consumer (D2C) & Retail"
        branch = "Growth & Marketing"
    elif any(x in industry or x in notes for x in ["startup", "founder", "funded", "venture"]):
        matched_offer = "VC-backed Startups & Founders List"
        icp_fit = "High-Growth Startup Ecosystem"
        branch = "Founders Office / Business Development"
    elif any(x in industry or x in notes for x in ["recruit", "hr", "staffing", "talent", "headhunter"]):
        matched_offer = "Active Job Seekers & Professionals Database"
        icp_fit = "Talent Acquisition & Staffing Agency"
        branch = "Recruiting / HR Ops"
    elif any(x in industry or x in notes for x in ["health", "medical", "clinic", "dentist", "doctor", "hospital"]):
        matched_offer = "Local Healthcare & Medical Clinics Directory"
        icp_fit = "Healthcare Providers & Medical Clinics"
        branch = "Practice Operations"
    else:
        matched_offer = "Custom B2B List Enrichment Service"
        icp_fit = "B2B Professional Services & Consulting"
        branch = "Outbound Sales Development"

    offer_info = OFFERS[matched_offer]
    pain_point = offer_info["pain_points"][0]
    usecase = offer_info["usecase"]

    # Calculate dynamic mock score (0-100)
    score = 50
    
    # Title Relevance
    if any(x in title for x in ["ceo", "founder", "president", "chief"]):
        score += 25
    elif any(x in title for x in ["vp", "vice president", "director", "head"]):
        score += 20
    elif any(x in title for x in ["manager", "lead"]):
        score += 10
    else:
        score += 5
        
    # Company Size Relevance
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
            # Fallback range matching
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

    # Industry Relevance
    if matched_offer != "Custom B2B List Enrichment Service":
        score += 10
    else:
        score += 5

    # Location Relevance
    location = lead.get("location", "").lower()
    if any(x in location for x in ["united states", "us", "uk", "canada", "london", "york", "california", "texas"]):
        score += 5
    else:
        score += 2

    # Deterministic variation (0-9) to make scores unique and realistic per lead
    email = lead.get("email", "")
    variation = sum(ord(c) for c in email) % 10
    score += variation

    # Cap score at 100
    score = min(score, 100)


    matched_segment = {
        "icp_fit": icp_fit,
        "branch_target": branch,
        "pain_point": pain_point,
        "go4db_offer": matched_offer,
        "data_usecase": usecase
    }

    # Draft Initial Pitch
    initial_subject = f"Growing outbound leads for {company}?"
    initial_body = (
        f"Hi {first_name},\n\n"
        f"I was looking at {company} and noticed your focus on B2B client acquisition. "
        f"Typically, companies like yours run into the bottleneck of {pain_point.lower()}.\n\n"
        f"At Go4Database, we recently compiled our \"{matched_offer}\" which includes over "
        f"350 million business contacts globally. For {company}, this could be used {usecase.lower()}.\n\n"
        f"We've verified all emails and LinkedIn profiles to keep bounce rates under 5%.\n\n"
        f"Would you be open to a quick look at a sample sheet of 20 leads matching your ICP next week?\n\n"
        f"Best regards,\n"
        f"[Sender Name]\n"
        f"Go4Database Sales"
    )

    # Draft Follow Up 1 (Nudge + value sample)
    fu1_subject = f"Re: Sample leads for {company}?"
    fu1_body = (
        f"Hi {first_name},\n\n"
        f"I know you are likely busy, so I put together a quick sample segment of 5 verified contacts "
        f"directly matching your ideal buyer profile. Here is what they look like:\n\n"
        f"1. Director of Growth, tech startup (verified business email + direct dial)\n"
        f"2. VP of Marketing, retail brand (verified business email + LinkedIn URL)\n"
        f"3. Head of Sales, mid-market IT services company\n\n"
        f"We have thousands more contacts in this exact segment. "
        f"If you'd like to get the full list to test with your outreach tool, let me know when is a good time to connect.\n\n"
        f"Best,\n"
        f"[Sender Name]"
    )

    # Draft Follow Up 2 (Soft break up)
    fu2_subject = f"Closing the loop / {company}"
    fu2_body = (
        f"Hi {first_name},\n\n"
        f"I haven't heard back, so I'll assume that growing your database of prospects isn't a priority for {company} right now.\n\n"
        f"If things change, or if you'd like to browse our list directory at Go4Database down the road, "
        f"feel free to reach out anytime.\n\n"
        f"If you aren't the right contact for B2B lists, I'd appreciate it if you could point me to who is. "
        f"Otherwise, this is the last email you'll receive from me.\n\n"
        f"Thanks,\n"
        f"[Sender Name]"
    )

    drafts = {
        "initial_pitch": {"subject": initial_subject, "body": initial_body},
        "follow_up_1": {"subject": fu1_subject, "body": fu1_body},
        "follow_up_2": {"subject": fu2_subject, "body": fu2_body}
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
You are an expert AI sales outreach agent working for "Go4Database". 
Go4Database is a B2B lead generation database provider with 350M+ records globally.

Your task is to analyze the prospect's profile and match them to the single best Go4Database database list, enrichment, or use case. Then, generate a personalized, high-converting 3-step email sequence.

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

Please generate the following in a JSON structure:
1. "matched_segment":
   - "icp_fit": Short description of the prospect's business model/ICP
   - "branch_target": The specific department at the prospect's company that would benefit most (e.g. Outbound Sales, Marketing, Recruiting, Founder's Office)
   - "pain_point": A major lead generation, sales, or recruitment pain point they likely experience
   - "go4db_offer": The name of the EXACT matching Go4Database list/service from the list above.
   - "data_usecase": A highly specific use case explaining how the prospect can use the Go4Database list to grow their own revenue.
2. "score": An outreach fit score between 0 and 100 based on company size, title, and relevance of the offer.
3. "email_drafts":
   - "initial_pitch": Subject and Body. This should be short (under 150 words), direct, personalized, professional, and end with a clear Call to Action (like offering a 20-lead sample list). Place [Sender Name] as a placeholder for the sender.
   - "follow_up_1": Subject and Body. A gentle nudge sent 3 days later, adding value (e.g., offering to show a customized sample data structure of their target audience).
   - "follow_up_2": Subject and Body. A final soft close sent 7 days later to close the loop politely.

Your response must be ONLY valid JSON, with no other text, markdown blocks or preambles.
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
     "follow_up_2": {{ "subject": "string", "body": "string" }}
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

def classify_reply_fallback(reply_body: str) -> Tuple[str, str]:
    """
    Fallback keyword-based sentiment classifier.
    """
    cleaned_body = strip_reply_history(reply_body)
    body_lower = cleaned_body.lower()
    body_norm = body_lower.replace("'", "").replace("’", "").replace("`", "")
    
    # Check Out of Office
    ooo_keywords = ["out of office", "vacation", "annual leave", "ooo", "snooze", "until i return", "returning on", "away from my"]
    if any(x in body_norm for x in ooo_keywords):
        return "OOO", "The responder is currently out of office."
    
    # Check Wrong Contact
    wrong_contact_keywords = ["not the right person", "wrong contact", "wrong person", "try contacting", "not in charge", "forwarded to", "not the person"]
    if any(x in body_norm for x in wrong_contact_keywords):
        return "Wrong_Contact", "The responder indicates they are not the correct decision maker."

    # Check Not Interested
    not_interested_keywords = [
        "not interested", "not intrested", "no interest", "no intrest",
        "unsubscribe", "remove", "stop", "dont send", "dont email", 
        "dont mail", "stop mailing", "stop emailing", "stop sending", 
        "please dont", "please do not", "no thanks", "not looking",
        "dont write", "no further", "dont contact", "do not contact"
    ]
    if any(x in body_norm for x in not_interested_keywords):
        return "Not_Interested", "The responder is not interested in Go4Database products."

    # Check Interested
    interested_keywords = [
        "interested", "intrested", "pricing", "cost", "demo", "sample", 
        "send me", "call", "zoom", "schedule", "sounds good", 
        "please send", "details", "info", "information"
    ]
    if any(x in body_norm for x in interested_keywords):
        return "Interested", "The responder asked for pricing, details, a sample, or a call."

    # Default to Needs Follow-up
    return "Needs_Follow_Up_Pending", "The reply contains questions or requires customized follow-up."


def classify_reply(lead: Dict[str, Any], reply_body: str, api_key: str = "") -> Tuple[str, str]:
    """
    Classifies a prospect's email reply using Gemini.
    Outputs: (Status, Explanation)
    Status must be one of: Interested, Not_Interested, OOO, Wrong_Contact, Needs_Follow_Up_Pending
    """
    cleaned_reply = strip_reply_history(reply_body)
    if not api_key:
        return classify_reply_fallback(cleaned_reply)

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        history_str = ""
        for hist in lead.get("history", []):
            if "Email Sent" in hist.get("action", "") or "Follow-up" in hist.get("action", ""):
                history_str += f"- {hist.get('action')}: {hist.get('details')}\n"

        prompt = f"""
You are an email sales assistant for Go4Database. You need to analyze the reply received from a prospect and classify it into one of the following category codes:
- "Interested" (Prospect wants pricing, a meeting, a sample list, more details, or expresses positive intent)
- "Not_Interested" (Prospect explicitly refuses, says no thanks, requests opt-out/unsubscribe, or has negative intent)
- "OOO" (Out of office autoreply, vacation notice, away, etc.)
- "Wrong_Contact" (Prospect states they are not the correct person and/or points to a different person/department)
- "Needs_Follow_Up_Pending" (Prospect asks complex questions, seeks clarifications, or the response doesn't fit standard categories but is not negative)

Prospect Info:
- Name: {lead.get('name')}
- Company: {lead.get('company')}
- Offer Matched: {lead.get('matched_segment', {}).get('go4db_offer')}

Outbound Campaign History:
{history_str}

Incoming Reply:
\"\"\"
{cleaned_reply}
\"\"\"

Please analyze the email and return a JSON response containing:
1. "category": The exact category code from the list above.
2. "reason": A brief 1-sentence reason for the classification.

Output ONLY a valid JSON object. No other text.
{{
  "category": "Interested" | "Not_Interested" | "OOO" | "Wrong_Contact" | "Needs_Follow_Up_Pending",
  "reason": "reason string"
}}
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return data["category"], data["reason"]
    except Exception as e:
        print(f"Gemini reply classification failed: {e}. Using fallback.")
        return classify_reply_fallback(cleaned_reply)


def generate_custom_followup(lead: Dict[str, Any], reply_body: str, category: str, api_key: str = "") -> str:
    """
    Generates a personalized response back to the prospect's reply.
    Used for Interested or Needs_Follow_Up replies to move them along the funnel.
    """
    name_parts = (lead.get("name") or "there").split()
    name = name_parts[0] if name_parts else "there"
    company = lead.get("company", "your company")
    offer = lead.get("matched_segment", {}).get("go4db_offer", "B2B Lists")

    if not api_key:
        # Fallback responses
        if category == "Interested":
            return (
                f"Hi {name},\n\n"
                f"Thanks for the quick response! I'm thrilled you'd like to take a look at the {offer}.\n\n"
                f"I've attached a customized sample of 15 contacts in Excel format matching your criteria. "
                f"You can also schedule a brief 5-minute call using my calendar link: [Calendar Link].\n\n"
                f"Let me know what you think of the sample records!\n\n"
                f"Best,\n"
                f"[Sender Name]"
            )
        else: # Needs Follow up
            return (
                f"Hi {name},\n\n"
                f"Thanks for reaching out with your question.\n\n"
                f"Regarding our {offer}: we update and re-verify email addresses every 30 days. "
                f"We also offer custom appending if you have specific criteria not covered in our standard categories.\n\n"
                f"I'd be happy to show you a demo of the portal. Do you have a few minutes for a quick call next week?\n\n"
                f"Best,\n"
                f"[Sender Name]"
            )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""
You are a sales agent at Go4Database. You need to write a personalized email response to a lead who has just replied.

Lead Name: {lead.get('name')}
Lead Company: {lead.get('company')}
Go4Database Offer Matched: {offer}
Category of lead reply: {category}

Prospect's incoming email:
\"\"\"
{reply_body}
\"\"\"

Write a short, professional, sales-focused response that addresses their reply directly, reinforces Go4Database's value proposition, and secures the next step (booking a meeting or trying a sample). Keep it under 120 words. Use [Sender Name] as the signature placeholder.

Output only the email body.
"""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini custom follow-up generation failed: {e}. Using fallback.")
        return generate_custom_followup(lead, reply_body, category, api_key="")
