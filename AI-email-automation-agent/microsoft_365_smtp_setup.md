# Microsoft 365 SMTP AUTH Setup Guide

This document provides step-by-step instructions on how to configure Microsoft 365 (Office 365) email accounts to work with the **Go4Database AI Outreach Agent** portal. 

Because Microsoft blocks legacy authentication protocols by default, you must follow these steps to allow the web app to log in and send emails using your custom Microsoft 365 domains.

---

## 📋 The Setup Workflow

To successfully connect a Microsoft 365 account, you must complete three phases:
1. **Phase 1:** Disable global "Security Defaults" in the Microsoft Entra Portal.
2. **Phase 2:** Enable the SMTP protocol for the mailbox in the Microsoft 365 Admin Center.
3. **Phase 3 (If needed):** Run PowerShell commands to force Microsoft's backend database to accept SMTP connections (bypassing Microsoft UI sync bugs).

---

## 🔑 Phase 1: Disable "Security Defaults" (Admin Portal)
*You must be a Global Administrator to perform this.*

1. Go to the **Microsoft Entra admin center**:
   👉 [https://entra.microsoft.com/](https://entra.microsoft.com/)
2. On the left menu, select **Identity** -> **Overview**.
3. In the main window, click on the **Properties** tab.
4. Scroll to the bottom of the page and click **Manage security defaults**.
5. Set **Security defaults** to **Disabled**.
6. Select a reason (e.g., *"My organization uses legacy clients/protocols"*) and click **Save**.

---

## ✉️ Phase 2: Enable SMTP for the Mailbox
*You must do this for each mailbox you want to add to the rotation pool.*

1. Go to the **Microsoft 365 admin center**:
   👉 [https://admin.microsoft.com/](https://admin.microsoft.com/)
2. Switch off the **"Simplified view"** (found at the top left of the active users list) to ensure all tabs are visible.
3. Go to **Users** -> **Active users** and select the mailbox (e.g., `anna@listgo4database.com`).
4. In the flyout panel on the right, click the **Mail** tab.
5. Under **Email apps**, click **Manage email apps**.
6. Check/tick the **Authenticated SMTP** box.
7. Click **Save changes**.

---

## 💻 Phase 3: Force Enable via PowerShell (Fixes UI Mismatch Bugs)
Sometimes the web portal says SMTP is enabled, but Microsoft's backend database continues to block connections. Running these commands will force the block open.

### On macOS (Mac):
1. **Install PowerShell:**
   Download and install the official macOS installer pkg:
   👉 [Download PowerShell for Mac (.pkg)](https://github.com/PowerShell/PowerShell/releases/download/v7.4.2/powershell-7.4.2-osx-x64.pkg)
2. **Start PowerShell:**
   Open your Mac **Terminal** app and type:
   ```bash
   pwsh
   ```
3. **Install & Run Exchange Cmdlets:**
   Paste these commands into the shell:
   ```powershell
   # 1. Install module (only needed once)
   Install-Module -Name ExchangeOnlineManagement -RequiredVersion 3.0.0 -Force -Scope CurrentUser -AllowClobber
   
   # 2. Connect to Exchange (Log in with your ADMIN account in the pop-up window)
   Connect-ExchangeOnline
   
   # 3. Enable SMTP AUTH globally for the entire company/tenant
   Set-TransportConfig -SmtpClientAuthenticationDisabled $false
   
   # 4. Enable SMTP AUTH for the specific email address
   Set-CASMailbox -Identity "YOUR_EMAIL@YOURDOMAIN.COM" -SmtpClientAuthenticationDisabled $false
   
   # 5. Disconnect and exit
   Disconnect-ExchangeOnline
   exit
   ```

### On Windows:
1. Right-click the Start menu and open **PowerShell (Run as Administrator)**.
2. Run the same commands listed above starting from **Step 3**.

---

## ⚙️ Phase 4: Configure in the AI Outreach Portal

Once Microsoft has saved the changes (this can take 5–15 minutes to propagate globally), add the account to your portal:

1. Log in to your outreach portal at `https://go4database.in/` and navigate to **Settings**.
2. Scroll to **Add Additional Sender Account** and fill in:
   * **Sender Name:** The display name (e.g. `Anna Scott`)
   * **SMTP/IMAP Username (Email):** The email address (e.g. `anna@listgo4database.com`)
   * **Password / App Password:** The standard email login password
   * **SMTP Server:** `smtp.office365.com`
   * **SMTP Port:** `587`
   * **IMAP Server (Optional):** `outlook.office365.com`
   * **IMAP Port:** `993`
3. Click **Add Account to Pool**.

> [!NOTE]
> **Important Note on IMAP (Reply Tracking):**
> Microsoft has permanently disabled standard password logins for **IMAP (checking inbox)**. The outreach portal will still successfully send emails using Anna's account, but it will show an `IMAP connection failed` error in the logs.
> 
> You will need to check Anna's mailbox manually for replies and click the "Qualify/MQL" button in the portal if someone replies.
