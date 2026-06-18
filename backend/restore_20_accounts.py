import sqlite3
import json
import os
import sys

# Define target database paths to try
DB_PATHS = [
    "db/campaign_state.db",
    "backend/db/campaign_state.db",
    "/home/go4database.in/db/campaign_state.db",
    "/home/go4database.in/backend/db/campaign_state.db"
]

SENDER_ACCOUNTS = [
  {
    "id": "rot_1781509283257_1dcnt",
    "name": "Anna",
    "smtp_user": "anna@heygo4database.com",
    "smtp_password": "xtvqfssxdhpdujgi",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509310081_5bi6b",
    "name": "Sam",
    "smtp_user": "sam@heygo4database.com",
    "smtp_password": "oonatudhugobkjqd",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509334188_x6pyv",
    "name": "Sam",
    "smtp_user": "sam@teamgo4database.com",
    "smtp_password": "xkcrqwgaitvaggna",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509353981_jtchx",
    "name": "Anna",
    "smtp_user": "anna@teamgo4database.com",
    "smtp_password": "pkmmvezcdytspziw",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509369190_jck0k",
    "name": "Sam",
    "smtp_user": "sam@joingo4database.com",
    "smtp_password": "cqkslmltezevzpdm",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509383581_dc4nl",
    "name": "Anna",
    "smtp_user": "anna@joingo4database.com",
    "smtp_password": "kwgwlmmaknobdxng",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509399617_6da9m",
    "name": "Sam",
    "smtp_user": "sam@mygo4database.com",
    "smtp_password": "zszhpguleizviahr",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509415316_z852m",
    "name": "Anna",
    "smtp_user": "anna@mygo4database.com",
    "smtp_password": "wksqtatsyadultpv",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509435002_g6w1w",
    "name": "Sam",
    "smtp_user": "sam@getgo4database.com",
    "smtp_password": "fzzprycwseoohqqu",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781509450924_8aid6",
    "name": "Anna",
    "smtp_user": "anna@getgo4database.com",
    "smtp_password": "fqhzqldzjijzfkos",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781510289682_9kkc3",
    "name": "Sam",
    "smtp_user": "sam@trygo4database.com",
    "smtp_password": "vcpmbucestkywshw",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781510304915_7gh78",
    "name": "Anna",
    "smtp_user": "anna@trygo4database.com",
    "smtp_password": "tcuzatiatiodegvd",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781510318099_hssvz",
    "name": "Sam",
    "smtp_user": "sam@usego4database.com",
    "smtp_password": "eianjqdocmfrhvnj",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781510328925_sheu6",
    "name": "Anna",
    "smtp_user": "anna@usego4database.com",
    "smtp_password": " thcahraulriyqmpe",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "imap_server": "",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_1781707193441_bq3l5",
    "name": "Anna Scott",
    "smtp_user": "anna@listgo4database.com",
    "smtp_password": "Lane@#$14",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_39e7ed7d",
    "name": "Sam Anderson",
    "smtp_user": "sam@listgo4database.com",
    "smtp_password": "G$413127785505ud",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_d7f36e44",
    "name": "Anna Scott",
    "smtp_user": "anna@newgo4database.com",
    "smtp_password": "N#982064529749ur",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_d0432271",
    "name": "Sam Anderson",
    "smtp_user": "sam@newgo4database.com",
    "smtp_password": "Q$220418148633uk",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_82512977",
    "name": "Anna Scott",
    "smtp_user": "anna@meetgo4database.com",
    "smtp_password": "D%633602791511oy",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  },
  {
    "id": "rot_e8b0bafe",
    "name": "Sam Anderson",
    "smtp_user": "sam@meetgo4database.com",
    "smtp_password": "Z$708871873494ob",
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "is_active": True
  }
]

def restore():
    # Find database file
    db_path = None
    for p in DB_PATHS:
        if os.path.exists(p):
            db_path = p
            break
            
    if not db_path:
        print("ERROR: Could not find database file 'campaign_state.db'. Please run this from the project root directory.")
        sys.exit(1)
        
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Write to database settings
    accounts_json = json.dumps(SENDER_ACCOUNTS)
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sender_accounts', ?)", (accounts_json,))
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: Successfully restored {len(SENDER_ACCOUNTS)} sender accounts in database settings!")

if __name__ == "__main__":
    restore()
