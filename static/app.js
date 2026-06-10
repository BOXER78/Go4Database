// State Management
let state = {
    leads: [],
    logs: [],
    settings: {},
    campaignStatus: {},
    selectedLeadId: null,
    activeSeqTab: 'initial_pitch',
    campaigns: [],
    activeCampaignId: null,
    users: [],
    currentUser: null
};

// Polling interval ID
let pollingIntervalId = null;

// Document Ready
document.addEventListener("DOMContentLoaded", () => {
    initAuth();
    
    initTabs();
    initUpload();
    initSettings();
    initCampaignControls();
    initEmailEditor();
    initCampaignSelector();
    initSessionsDashboard();
    initTeamManagementUI();
    initLogoutButton();
    initLoginForm();
    
    // Hook Hot Leads Assignee Filter
    const filterEl = document.getElementById("hot-leads-assignee-filter");
    if (filterEl) {
        filterEl.addEventListener("change", () => {
            renderHotLeadsTable();
        });
    }
});

// Tab Management
function initTabs() {
    const navItems = document.querySelectorAll(".nav-item");
    const panes = document.querySelectorAll(".tab-pane");
    const pageTitle = document.getElementById("page-title");
    const pageSubtitle = document.getElementById("page-subtitle");

    const titles = {
        'sessions': { title: 'Campaign Sessions', sub: 'Create, monitor, and manage your email outreach campaigns.' },
        'overview': { title: 'Overview', sub: 'Outreach performance, automation control, and activity logs.' },
        'import': { title: 'Import Leads', sub: 'Upload files or paste spreadsheets to load outreach targets.' },
        'leads': { title: 'Leads & ICP Matching', sub: 'Analyze ideal customer profile fit and Go4Database service matches.' },
        'hot-leads': { title: 'Hot Leads (Interested Prospects)', sub: 'Centralized directory of interested prospects who replied positively. Copy details or reply directly.' },
        'replies': { title: 'Replies Inbox', sub: 'Review replies received from email targets and their automated AI classifications.' },
        'email-preview': { title: 'Email Editor', sub: 'Review, customize, and edit AI personalized sequence drafts.' },
        'settings': { title: 'Settings', sub: 'Configure API keys, SMTP credentials, and sequence automation parameters.' }
    };

    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const tab = item.getAttribute("data-tab");
            
            navItems.forEach(n => n.classList.remove("active"));
            panes.forEach(p => p.classList.remove("active"));
            
            item.classList.add("active");
            document.getElementById(`tab-${tab}`).classList.add("active");
            
            pageTitle.textContent = titles[tab].title;
            pageSubtitle.textContent = titles[tab].sub;

            // Trigger data updates on specific tabs
            if (tab === 'sessions') {
                renderSessionsPage();
            } else if (tab === 'leads') {
                renderLeadsTable();
            } else if (tab === 'hot-leads') {
                renderHotLeadsTable();
            } else if (tab === 'replies') {
                renderRepliesTable();
            } else if (tab === 'email-preview') {
                renderOutreachQueue();
            }
        });
    });

    // Set initial title based on active tab button
    const activeNav = document.querySelector(".nav-item.active");
    if (activeNav) {
        const initialTab = activeNav.getAttribute("data-tab");
        if (titles[initialTab]) {
            pageTitle.textContent = titles[initialTab].title;
            pageSubtitle.textContent = titles[initialTab].sub;
        }
    }

    // Handle links in Quickstart panel
    document.querySelectorAll(".tab-link").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const target = link.getAttribute("data-target");
            const navBtn = document.getElementById(`nav-${target}`);
            if (navBtn) navBtn.click();
        });
    });
}

// Fetch settings and API key status
async function fetchSettings() {
    if (state.currentUser && state.currentUser.role === "Sales Rep") {
        return;
    }
    try {
        const res = await fetch("/api/settings");
        state.settings = await res.json();
        populateSettingsInputs();
        
        // Update warning status
        const warning = document.getElementById("key-warning");
        const statusConfigured = document.getElementById("api-key-configured-status");
        const keyInput = document.getElementById("settings-api-key");
        
        if (state.settings.gemini_api_key) {
            warning.style.display = "none";
            if (statusConfigured) statusConfigured.style.display = "block";
            if (keyInput) keyInput.value = state.settings.gemini_api_key;
        } else {
            warning.style.display = "flex";
            if (statusConfigured) statusConfigured.style.display = "none";
        }
    } catch (e) {
        console.error("Error fetching settings:", e);
    }
}

// Fetch Campaign Status, Leads, and Logs
async function fetchState() {
    try {
        const role = state.currentUser ? state.currentUser.role : "Sales Rep";
        
        if (role !== "Sales Rep") {
            // Fetch campaigns list dynamically to keep dropdown in sync
            await fetchCampaigns();
            
            // 1. Fetch Campaign Status
            const resStatus = await fetch("/api/campaign/status");
            state.campaignStatus = await resStatus.json();
            updateCampaignButtons();
            updateOverviewMetrics();
        }
        
        // Fetch Users
        const resUsers = await fetch("/api/users");
        if (resUsers.ok) {
            state.users = await resUsers.json();
            if (role === "Admin") {
                renderTeamMembersTable();
            }
        }
        
        // 2. Fetch Leads
        const resLeads = await fetch("/api/leads");
        state.leads = await resLeads.json();
        
        if (role !== "Sales Rep") {
            // Update setup steps UI
            updateSetupSteps();
        }
        
        // If on sessions page, keep it updated
        if (document.getElementById("tab-sessions").classList.contains("active")) {
            renderSessionsPage();
        }
        
        // If on leads page, keep it updated
        if (document.getElementById("tab-leads").classList.contains("active")) {
            renderLeadsTable();
        }
        
        // If on hot leads page, keep it updated
        if (document.getElementById("tab-hot-leads").classList.contains("active")) {
            renderHotLeadsTable();
        }
        
        // If on replies page, keep it updated
        if (document.getElementById("tab-replies").classList.contains("active")) {
            renderRepliesTable();
        }
        
        // If on email preview page, refresh queue counts/statuses
        if (document.getElementById("tab-email-preview").classList.contains("active")) {
            renderOutreachQueue(false); // don't force select
        }
        
        if (role !== "Sales Rep") {
            // 3. Fetch Logs
            const resLogs = await fetch("/api/campaign/logs");
            state.logs = await resLogs.json();
            renderLogsTerminal();
        }
        
    } catch (e) {
        console.error("Error polling state:", e);
    }
}

// Fetch Campaign sessions list
async function fetchCampaigns() {
    if (state.currentUser && state.currentUser.role === "Sales Rep") {
        return;
    }
    try {
        const resList = await fetch("/api/campaigns");
        const campaigns = await resList.json();
        
        const resActive = await fetch("/api/campaigns/active");
        const { active_campaign_id } = await resActive.json();
        
        state.campaigns = campaigns;
        state.activeCampaignId = active_campaign_id;
        
        const select = document.getElementById("campaign-select");
        if (select) {
            // Check if active element is select. If so, skip rendering option list to avoid disrupting user interaction
            if (document.activeElement !== select) {
                // To minimize DOM operations, let's compare if option list is different
                const newHtml = campaigns.map(c => `<option value="${c.id}" ${c.id === active_campaign_id ? 'selected' : ''}>${c.name} (${c.size} leads)</option>`).join("");
                const currentHtml = Array.from(select.options).map(o => `<option value="${o.value}" ${o.selected ? 'selected' : ''}>${o.textContent}</option>`).join("");
                
                if (newHtml !== currentHtml) {
                    select.innerHTML = "";
                    campaigns.forEach(c => {
                        const opt = document.createElement("option");
                        opt.value = c.id;
                        opt.textContent = `${c.name} (${c.size} leads)`;
                        if (c.id === active_campaign_id) {
                            opt.selected = true;
                        }
                        select.appendChild(opt);
                    });
                }
            } else {
                if (select.value !== active_campaign_id) {
                    select.value = active_campaign_id;
                }
            }
        }
    } catch (e) {
        console.error("Error fetching campaigns:", e);
    }
}

// Initialize active switching and deletion interactions
function initCampaignSelector() {
    const select = document.getElementById("campaign-select");
    if (select) {
        select.addEventListener("change", async () => {
            const campaignId = select.value;
            try {
                const res = await fetch(`/api/campaigns/active/${campaignId}`, {
                    method: "POST"
                });
                if (res.ok) {
                    state.selectedLeadId = null;
                    document.getElementById("email-editor-workspace").style.display = "none";
                    document.getElementById("email-editor-empty-state").style.display = "block";
                    state.activeCampaignId = campaignId;
                    await fetchState();
                }
            } catch (e) {
                alert("Failed to switch campaign: " + e);
            }
        });
    }

    const btnDelete = document.getElementById("btn-delete-campaign");
    if (btnDelete) {
        btnDelete.addEventListener("click", async () => {
            const campaignId = state.activeCampaignId;
            if (!campaignId) return;
            
            const campaign = state.campaigns.find(c => c.id === campaignId);
            const name = campaign ? campaign.name : "this session";
            
            if (confirm(`Are you sure you want to delete "${name}"? All leads, logs, and drafts for this session will be permanently deleted.`)) {
                try {
                    const res = await fetch(`/api/campaigns/delete/${campaignId}`, {
                        method: "POST"
                    });
                    if (res.ok) {
                        state.selectedLeadId = null;
                        document.getElementById("email-editor-workspace").style.display = "none";
                        document.getElementById("email-editor-empty-state").style.display = "block";
                        await fetchCampaigns();
                        await fetchState();
                    }
                } catch (e) {
                    alert("Failed to delete campaign: " + e);
                }
            }
        });
    }
}

// Update settings values on screens
function initSettings() {
    const btnSave = document.getElementById("btn-save-settings");
    
    btnSave.addEventListener("click", async () => {
        const settings = {
            gemini_api_key: document.getElementById("settings-api-key").value.trim ? document.getElementById("settings-api-key").value.trim() : document.getElementById("settings-api-key").value,
            smtp_server: document.getElementById("settings-smtp-server").value,
            smtp_port: parseInt(document.getElementById("settings-smtp-port").value) || 587,
            imap_server: document.getElementById("settings-imap-server").value,
            imap_port: parseInt(document.getElementById("settings-imap-port").value) || 993,
            smtp_user: document.getElementById("settings-smtp-user").value,
            smtp_password: document.getElementById("settings-smtp-pass").value,
            sender_name: document.getElementById("settings-sender-name").value,
            sender_email: document.getElementById("settings-sender-email").value,
            daily_limit: parseInt(document.getElementById("settings-limit").value) || 50,
            min_delay: parseInt(document.getElementById("settings-min-delay").value) || 5,
            auto_followup_delay_days: parseFloat(document.getElementById("settings-followup-delay").value) || 24,
            automation_mode: document.getElementById("settings-auto-mode").checked,
            sender_accounts: state.settings.sender_accounts || []
        };
        
        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(settings)
            });
            const data = await res.json();
            if (data.status === "success") {
                state.settings = data.settings;
                alert("Settings saved successfully!");
                fetchSettings();
            }
        } catch (e) {
            alert("Failed to save settings: " + e);
        }
    });

    initRotationAccountsUI();
}

// Populate Settings Form once loaded
function populateSettingsInputs() {
    if (!state.settings) return;
    
    document.getElementById("settings-api-key").value = state.settings.gemini_api_key || "";
    document.getElementById("settings-smtp-server").value = state.settings.smtp_server || "";
    document.getElementById("settings-smtp-port").value = state.settings.smtp_port || 587;
    document.getElementById("settings-imap-server").value = state.settings.imap_server || "";
    document.getElementById("settings-imap-port").value = state.settings.imap_port || 993;
    document.getElementById("settings-smtp-user").value = state.settings.smtp_user || "";
    document.getElementById("settings-smtp-pass").value = state.settings.smtp_password || "";
    document.getElementById("settings-sender-name").value = state.settings.sender_name || "";
    document.getElementById("settings-sender-email").value = state.settings.sender_email || "";
    document.getElementById("settings-limit").value = state.settings.daily_limit || 50;
    document.getElementById("settings-min-delay").value = state.settings.min_delay || 5;
    document.getElementById("settings-followup-delay").value = state.settings.auto_followup_delay_days || 24;
    document.getElementById("settings-auto-mode").checked = state.settings.automation_mode || false;

    renderRotationAccounts();
}

function renderRotationAccounts() {
    const tbody = document.getElementById("rotation-accounts-tbody");
    if (!tbody) return;
    
    tbody.innerHTML = "";
    const accounts = state.settings.sender_accounts || [];
    
    if (accounts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted" style="padding: 20px;">
                    No additional rotation accounts added yet. Primary sender account will be used exclusively.
                </td>
            </tr>
        `;
        return;
    }
    
    accounts.forEach(acc => {
        const tr = document.createElement("tr");
        
        const nameCell = document.createElement("td");
        nameCell.textContent = acc.name || "Unnamed";
        tr.appendChild(nameCell);
        
        const emailCell = document.createElement("td");
        emailCell.textContent = acc.smtp_user || "";
        tr.appendChild(emailCell);
        
        const smtpCell = document.createElement("td");
        smtpCell.textContent = `${acc.smtp_server}:${acc.smtp_port}`;
        tr.appendChild(smtpCell);
        
        const imapCell = document.createElement("td");
        imapCell.textContent = `${acc.imap_server || "Autodetect"}:${acc.imap_port || "993"}`;
        tr.appendChild(imapCell);
        
        // Status cell with toggle
        const statusCell = document.createElement("td");
        const isActive = acc.is_active !== false;
        
        const toggleLabel = document.createElement("label");
        toggleLabel.className = "toggle-switch-label";
        toggleLabel.style.display = "inline-flex";
        toggleLabel.style.alignItems = "center";
        
        const toggleInput = document.createElement("input");
        toggleInput.type = "checkbox";
        toggleInput.checked = isActive;
        toggleInput.addEventListener("change", () => toggleRotationAccountActive(acc.id));
        
        const toggleSlider = document.createElement("span");
        toggleSlider.className = "toggle-switch-slider";
        
        toggleLabel.appendChild(toggleInput);
        toggleLabel.appendChild(toggleSlider);
        statusCell.appendChild(toggleLabel);
        tr.appendChild(statusCell);
        
        // Actions cell with delete button
        const actionsCell = document.createElement("td");
        const btnDelete = document.createElement("button");
        btnDelete.className = "btn btn-secondary";
        btnDelete.style.padding = "4px 8px";
        btnDelete.style.fontSize = "11px";
        btnDelete.style.backgroundColor = "#ef4444";
        btnDelete.style.color = "#ffffff";
        btnDelete.style.border = "none";
        btnDelete.style.borderRadius = "4px";
        btnDelete.style.cursor = "pointer";
        btnDelete.textContent = "Delete";
        btnDelete.addEventListener("click", () => deleteRotationAccount(acc.id));
        
        actionsCell.appendChild(btnDelete);
        tr.appendChild(actionsCell);
        
        tbody.appendChild(tr);
    });
}

async function saveRotationAccountsToServer() {
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(state.settings)
        });
        const data = await res.json();
        if (data.status === "success") {
            state.settings = data.settings;
            renderRotationAccounts();
        }
    } catch (e) {
        console.error("Failed to sync rotation accounts:", e);
        alert("Failed to sync rotation accounts with backend: " + e);
    }
}

function toggleRotationAccountActive(id) {
    if (!state.settings.sender_accounts) return;
    const acc = state.settings.sender_accounts.find(a => a.id === id);
    if (acc) {
        acc.is_active = (acc.is_active === false) ? true : false;
        saveRotationAccountsToServer();
    }
}

function deleteRotationAccount(id) {
    if (!state.settings.sender_accounts) return;
    if (confirm("Are you sure you want to remove this account from the rotation pool?")) {
        state.settings.sender_accounts = state.settings.sender_accounts.filter(a => a.id !== id);
        saveRotationAccountsToServer();
    }
}

function initRotationAccountsUI() {
    const btnAdd = document.getElementById("btn-add-rotation-account");
    if (!btnAdd) return;
    
    btnAdd.addEventListener("click", () => {
        const nameVal = document.getElementById("rotation-name").value.trim();
        const userVal = document.getElementById("rotation-user").value.trim();
        const passVal = document.getElementById("rotation-pass").value;
        const smtpServerVal = document.getElementById("rotation-smtp-server").value.trim();
        const smtpPortVal = parseInt(document.getElementById("rotation-smtp-port").value) || 587;
        const imapServerVal = document.getElementById("rotation-imap-server").value.trim();
        const imapPortVal = parseInt(document.getElementById("rotation-imap-port").value) || 993;
        
        if (!nameVal || !userVal || !passVal) {
            alert("Sender Name, Username (Email), and Password are required fields.");
            return;
        }
        
        if (!state.settings.sender_accounts) {
            state.settings.sender_accounts = [];
        }
        
        // Unique ID
        const newAcc = {
            id: "rot_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5),
            name: nameVal,
            smtp_user: userVal,
            smtp_password: passVal,
            smtp_server: smtpServerVal || "smtp.gmail.com",
            smtp_port: smtpPortVal,
            imap_server: imapServerVal,
            imap_port: imapPortVal,
            is_active: true
        };
        
        state.settings.sender_accounts.push(newAcc);
        saveRotationAccountsToServer();
        
        // Reset inputs
        document.getElementById("rotation-name").value = "";
        document.getElementById("rotation-user").value = "";
        document.getElementById("rotation-pass").value = "";
        document.getElementById("rotation-smtp-server").value = "smtp.gmail.com";
        document.getElementById("rotation-smtp-port").value = "587";
        document.getElementById("rotation-imap-server").value = "";
        document.getElementById("rotation-imap-port").value = "993";
    });
}

// Ingestion (Drag-and-Drop + Pasted Table)
function initUpload() {
    const dropzone = document.getElementById("file-dropzone");
    const fileInput = document.getElementById("lead-file-input");
    const btnPaste = document.getElementById("btn-paste-import");
    const pasteInput = document.getElementById("paste-input");
    const campaignNameInput = document.getElementById("import-campaign-name");
    
    // File browse
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });
    
    // Drag & Drop
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });
    
    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });
    
    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            uploadFile(e.dataTransfer.files[0]);
        }
    });
    
    // Paste upload
    btnPaste.addEventListener("click", async () => {
        const text = pasteInput.value.trim();
        if (!text) {
            alert("Please paste some comma or tab-delimited lead table data first.");
            return;
        }
        
        btnPaste.disabled = true;
        btnPaste.textContent = "Importing...";
        
        const campaignName = campaignNameInput ? campaignNameInput.value.trim() : "";
        const formData = new FormData();
        formData.append("pasted_data", text);
        if (campaignName) {
            formData.append("campaign_name", campaignName);
        }
        
        try {
            const res = await fetch("/api/leads/upload", {
                method: "POST",
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                alert(`Successfully ingested ${data.added_count} leads!`);
                pasteInput.value = "";
                if (campaignNameInput) campaignNameInput.value = "";
                await fetchCampaigns();
                document.getElementById("nav-leads").click();
            } else {
                alert("Import failed: " + data.detail);
            }
        } catch (e) {
            alert("Error sending pasted leads: " + e);
        } finally {
            btnPaste.disabled = false;
            btnPaste.textContent = "Import Pasted Data";
        }
    });
}

async function uploadFile(file) {
    const campaignNameInput = document.getElementById("import-campaign-name");
    const campaignName = campaignNameInput ? campaignNameInput.value.trim() : "";
    
    const formData = new FormData();
    formData.append("file", file);
    if (campaignName) {
        formData.append("campaign_name", campaignName);
    }
    
    const banner = document.querySelector(".dropzone-text");
    const originalText = banner.textContent;
    banner.textContent = `Uploading ${file.name}...`;
    
    try {
        const res = await fetch("/api/leads/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            alert(`File parsed successfully! Ingested ${data.added_count} leads.`);
            if (campaignNameInput) campaignNameInput.value = "";
            await fetchCampaigns();
            document.getElementById("nav-leads").click();
        } else {
            alert("Upload failed: " + data.detail);
        }
    } catch (e) {
        alert("Upload error: " + e);
    } finally {
        banner.textContent = originalText;
    }
}

// Campaign Play/Pause/Reset controls
function initCampaignControls() {
    const btnStart = document.getElementById("btn-start-campaign");
    const btnPause = document.getElementById("btn-pause-campaign");
    const btnReset = document.getElementById("btn-reset-campaign");
    
    btnStart.addEventListener("click", async () => {
        const res = await fetch("/api/campaign/start", { method: "POST" });
        if (res.ok) fetchState();
    });
    
    btnPause.addEventListener("click", async () => {
        const res = await fetch("/api/campaign/pause", { method: "POST" });
        if (res.ok) fetchState();
    });
    
    btnReset.addEventListener("click", async () => {
        if (confirm("WARNING: This will delete all lead database lists, campaign progress, drafts, and audit logs. Proceed?")) {
            const res = await fetch("/api/campaign/reset", { method: "POST" });
            if (res.ok) {
                state.selectedLeadId = null;
                document.getElementById("email-editor-workspace").style.display = "none";
                document.getElementById("email-editor-empty-state").style.display = "block";
                fetchState();
            }
        }
    });

    const btnClearLogs = document.getElementById("btn-clear-logs");
    btnClearLogs.addEventListener("click", () => {
        document.getElementById("agent-console").innerHTML = '<div class="log-line system">[SYSTEM] Console cleared locally. Waiting for new events...</div>';
    });
}

// Enable/Disable Campaign Buttons
function updateCampaignButtons() {
    const btnStart = document.getElementById("btn-start-campaign");
    const btnPause = document.getElementById("btn-pause-campaign");
    
    const isRunning = state.campaignStatus.is_running;
    const hasLeads = state.leads.length > 0;
    
    if (isRunning) {
        btnStart.disabled = true;
        btnPause.disabled = false;
    } else {
        btnStart.disabled = !hasLeads;
        btnPause.disabled = true;
    }
}

// Update Overview panel numbers
function updateOverviewMetrics() {
    const total = state.campaignStatus.total_leads || 0;
    const sent = state.campaignStatus.total_sent || 0;
    const replies = state.campaignStatus.total_replies || 0;
    const interested = state.campaignStatus.total_interested || 0;
    const notInterested = state.campaignStatus.total_not_interested || 0;
    const junk = state.campaignStatus.total_junk || 0;
    
    document.getElementById("val-total-leads").textContent = total;
    document.getElementById("val-total-sent").textContent = sent;
    document.getElementById("val-total-replies").textContent = replies;
    document.getElementById("val-total-interested").textContent = interested;
    document.getElementById("val-total-junk").textContent = junk;
    document.getElementById("val-total-not-interested").textContent = notInterested;
    
    // Funnel Percentages
    const progressPct = total > 0 ? Math.round((sent / total) * 100) : 0;
    const replyPct = sent > 0 ? Math.round((replies / sent) * 100) : 0;
    const interestPct = replies > 0 ? Math.round((interested / replies) * 100) : 0;
    
    document.getElementById("lbl-send-progress").textContent = `${progressPct}% of target sent`;
    document.getElementById("lbl-reply-rate").textContent = `${replyPct}% response rate`;
    document.getElementById("lbl-interest-rate").textContent = `${interestPct}% conversion rate`;
    
    // Visual Funnel Bars
    document.getElementById("lbl-funnel-ingested").textContent = total;
    document.getElementById("lbl-funnel-sent").textContent = sent;
    document.getElementById("lbl-funnel-replies").textContent = replies;
    document.getElementById("lbl-funnel-interested").textContent = interested;
    
    document.getElementById("bar-funnel-ingested").style.width = total > 0 ? "100%" : "0%";
    document.getElementById("bar-funnel-sent").style.width = total > 0 ? `${(sent / total) * 100}%` : "0%";
    document.getElementById("bar-funnel-replies").style.width = total > 0 ? `${(replies / total) * 100}%` : "0%";
    document.getElementById("bar-funnel-interested").style.width = total > 0 ? `${(interested / total) * 100}%` : "0%";
}

// Setup Flow Checklist logic
function updateSetupSteps() {
    const stepKey = document.getElementById("step-key");
    const stepUpload = document.getElementById("step-upload");
    const stepAnalyze = document.getElementById("step-analyze");
    const stepSend = document.getElementById("step-send");
    
    // 1. Key
    if (state.settings.gemini_api_key) {
        stepKey.classList.add("done");
    } else {
        stepKey.classList.remove("done");
    }
    
    // 2. Upload
    if (state.leads.length > 0) {
        stepUpload.classList.add("done");
    } else {
        stepUpload.classList.remove("done");
    }
    
    // 3. Analyze
    const analyzedLeads = state.leads.filter(l => l.status !== "Pending" && l.status !== "Analyzing");
    if (state.leads.length > 0 && analyzedLeads.length === state.leads.length) {
        stepAnalyze.classList.add("done");
    } else {
        stepAnalyze.classList.remove("done");
    }
    
    // 4. Send
    if (state.campaignStatus.is_running) {
        stepSend.classList.add("done");
    } else {
        stepSend.classList.remove("done");
    }
}

// Log Terminal Render
function renderLogsTerminal() {
    const consoleEl = document.getElementById("agent-console");
    if (!consoleEl) return;
    
    // Compare number of lines to avoid constant redraws if logs haven't changed
    const currentLinesCount = consoleEl.querySelectorAll(".log-line").length;
    if (state.logs.length === 0 && currentLinesCount <= 1) return;
    
    let html = "";
    state.logs.forEach(log => {
        const timeStr = new Date(log.timestamp).toLocaleTimeString();
        let classStr = "system";
        if (log.level === "INFO") classStr = "info";
        if (log.level === "AGENT") classStr = "agent";
        if (log.level === "ERROR") classStr = "error";
        
        html += `<div class="log-line ${classStr}"><span class="log-line timestamp">[${timeStr}]</span>[${log.level}] ${log.message}</div>`;
    });
    
    consoleEl.innerHTML = html || '<div class="log-line system">[SYSTEM] Ready. Waiting for events...</div>';
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

// Leads and Match Table Render
function renderLeadsTable() {
    const tbody = document.getElementById("leads-table-body");
    const countLabel = document.getElementById("lbl-leads-count");
    
    countLabel.textContent = `${state.leads.length} Leads Loaded`;
    
    if (state.leads.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="6" class="text-center py-5">
                    <div class="empty-state">
                        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                        <h4>No leads loaded yet</h4>
                        <p class="text-muted">Import leads via CSV or pastable tables to begin outreach.</p>
                    </div>
                </td>
            </tr>`;
        return;
    }
    
    let html = "";
    state.leads.forEach(lead => {
        const seg = lead.matched_segment;
        const offerStr = seg ? seg.go4db_offer : '<span class="text-muted">Not matched yet (Run AI)</span>';
        
        let fitDetailsStr = '<span class="text-muted">Run AI Agent to classify profile & select email angle</span>';
        if (seg) {
            fitDetailsStr = `
                <div class="fit-details-cell">
                    <label>ICP Match:</label>
                    <p>${seg.icp_fit}</p>
                    <label class="mt-1">Angle / Usecase:</label>
                    <p>${seg.data_usecase}</p>
                </div>`;
        }
        
        let scoreClass = "";
        if (lead.score >= 80) scoreClass = "high";
        else if (lead.score >= 50) scoreClass = "medium";
        const scoreStr = lead.score > 0 ? lead.score : "-";
        
        const statusClass = lead.status.toLowerCase();
        
        // Approve Toggle Switch
        const approvedChecked = lead.is_approved ? "checked" : "";
        const isAutoApproved = lead.score >= 80;
        const autoApprovedLabel = isAutoApproved ? '<span style="display: block; font-size: 9.5px; font-weight: 600; color: #16a34a; margin-top: 3px; text-align: right;">✓ Auto-Approved (80+)</span>' : '';
        const approveToggleHtml = lead.status === "Ready" ? `
            <div style="display: flex; flex-direction: column; align-items: flex-end;">
                <label class="toggle-switch-label" title="Approve this draft email sequence for automated delivery">
                    <input type="checkbox" ${approvedChecked} onchange="toggleApproveLead('${lead.id}')">
                    <span class="toggle-switch-slider"></span>
                    <span style="font-size: 11px;">Approved</span>
                </label>
                ${autoApprovedLabel}
            </div>` : "";
            
        html += `
            <tr id="row-${lead.id}">
                <td>
                    <div class="prospect-info-cell">
                        <h4>${lead.name}</h4>
                        <p>${lead.title} @ <strong>${lead.company}</strong></p>
                        <p class="text-muted">${lead.email} • ${lead.industry} • Size: ${lead.company_size}</p>
                    </div>
                </td>
                <td>${seg ? `<span class="segment-badge">${offerStr}</span>` : offerStr}</td>
                <td>${fitDetailsStr}</td>
                <td><span class="score-badge ${scoreClass}">${scoreStr}</span></td>
                <td><span class="status-pill ${statusClass}">${lead.status.replace(/_/g, ' ')}</span></td>
                <td class="actions-col">
                    <div class="leads-actions" style="display: flex; gap: 4px; flex-wrap: wrap;">
                        ${approveToggleHtml}
                        <button class="btn btn-secondary btn-mini" onclick="selectLeadForPreview('${lead.id}')" title="Preview generated outreach templates">Preview</button>
                        <button class="btn btn-secondary btn-mini" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Interested', 'Marked Interested', 'Marked manually as interested.')" title="Mark as Interested (Hot Lead)" style="border-color: var(--color-success); color: var(--color-success);">🔥 Hot</button>
                        <button class="btn btn-secondary btn-mini" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Not_Interested', 'Marked Uninterested', 'Marked manually as not interested.')" title="Mark as Not Interested" style="border-color: #64748b; color: #64748b;">Opt-out</button>
                        <button class="btn btn-secondary btn-mini text-danger" onclick="deleteLead('${lead.id}')" title="Remove lead from campaign">🗑</button>
                    </div>
                </td>
            </tr>`;
    });
    
    tbody.innerHTML = html;
}

// Bulk Run AI Ingest & Matching
const btnTriggerAnalysis = document.getElementById("btn-trigger-analysis");
if (btnTriggerAnalysis) {
    btnTriggerAnalysis.addEventListener("click", async () => {
        btnTriggerAnalysis.disabled = true;
        btnTriggerAnalysis.textContent = "AI Agent processing leads...";
        
        try {
            const res = await fetch("/api/leads/analyze", { method: "POST" });
            const data = await res.json();
            if (data.status === "success") {
                alert(`AI Outreach Agent is analyzing ${data.count} leads in the background.`);
                fetchState();
            } else if (data.status === "no_pending_leads") {
                alert("No pending leads to analyze. All leads are already matched or processed!");
            }
        } catch (e) {
            alert("Error launching analysis: " + e);
        } finally {
            btnTriggerAnalysis.disabled = false;
            btnTriggerAnalysis.textContent = "⚙ Run AI ICP Matching & Email Drafting";
        }
    });
}

// Lead actions (exposed globally for HTML onclick inline handlers)
window.deleteLead = async function(leadId) {
    if (confirm("Are you sure you want to delete this lead?")) {
        const res = await fetch(`/api/leads/delete/${leadId}`, { method: "POST" });
        if (res.ok) {
            state.leads = state.leads.filter(l => l.id !== leadId);
            if (state.selectedLeadId === leadId) {
                state.selectedLeadId = null;
                document.getElementById("email-editor-workspace").style.display = "none";
                document.getElementById("email-editor-empty-state").style.display = "block";
            }
            fetchState();
        }
    }
};

window.toggleApproveLead = async function(leadId) {
    const res = await fetch(`/api/leads/toggle-approve/${leadId}`, { method: "POST" });
    if (res.ok) {
        fetchState();
    }
};

window.selectLeadForPreview = function(leadId) {
    state.selectedLeadId = leadId;
    document.getElementById("nav-email-preview").click();
};

// Email Preview & Selector Panel
function renderOutreachQueue(forceSelectFirst = true) {
    const queueList = document.getElementById("queue-lead-list");
    if (!queueList) return;
    
    if (state.leads.length === 0) {
        queueList.innerHTML = `<li class="empty-state text-muted text-center py-4">No leads available</li>`;
        state.selectedLeadId = null;
        document.getElementById("email-editor-workspace").style.display = "none";
        document.getElementById("email-editor-empty-state").style.display = "block";
        return;
    }
    
    let html = "";
    state.leads.forEach(lead => {
        const activeClass = lead.id === state.selectedLeadId ? "active" : "";
        const hasDrafts = lead.email_drafts !== null;
        const offer = lead.matched_segment ? lead.matched_segment.go4db_offer : "Not Matched";
        
        let statusText = lead.status.replace(/_/g, ' ');
        if (lead.status === "Ready" && lead.is_approved) {
            statusText += lead.score >= 80 ? " (Auto-Approved)" : " (Approved)";
        }
        
        html += `
            <li class="queue-item ${activeClass}" onclick="selectLeadFromQueue('${lead.id}')">
                <h4>${lead.name}</h4>
                <p>${lead.company} • ${offer}</p>
                <div class="queue-item-meta">
                    <span class="status-pill ${lead.status.toLowerCase()}" style="font-size: 9px; padding: 2px 4px;">${statusText}</span>
                    <span class="score text-muted">Score: ${lead.score || '-'}</span>
                </div>
            </li>`;
    });
    
    queueList.innerHTML = html;
    
    // Auto-select first lead if nothing selected yet
    if (forceSelectFirst && !state.selectedLeadId && state.leads.length > 0) {
        selectLeadFromQueue(state.leads[0].id);
    } else if (state.selectedLeadId) {
        // Refresh details for currently selected lead
        populateEmailEditor(state.selectedLeadId);
    }
}

window.selectLeadFromQueue = function(leadId) {
    state.selectedLeadId = leadId;
    
    // Highlight list element
    const items = document.querySelectorAll(".queue-item");
    items.forEach(el => el.classList.remove("active"));
    
    // Find index
    const leadIndex = state.leads.findIndex(l => l.id === leadId);
    if (leadIndex !== -1) {
        const queueList = document.getElementById("queue-lead-list");
        const listItems = queueList.querySelectorAll(".queue-item");
        if (listItems[leadIndex]) listItems[leadIndex].classList.add("active");
    }
    
    populateEmailEditor(leadId);
};

// Populate Workspace Panel
function populateEmailEditor(leadId) {
    const lead = state.leads.find(l => l.id === leadId);
    if (!lead) return;
    
    const workspace = document.getElementById("email-editor-workspace");
    const emptyState = document.getElementById("email-editor-empty-state");
    
    if (lead.email_drafts === null) {
        workspace.style.display = "none";
        emptyState.style.display = "block";
        emptyState.innerHTML = `
            <div class="empty-state py-5">
                <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2z"/></svg>
                <h4>Lead Analysis Pending</h4>
                <p class="text-muted">This lead has not been matched or analyzed by the AI agent yet.</p>
                <button class="btn btn-primary btn-sm mt-3" onclick="triggerSingleAnalysis('${lead.id}')">Analyze Lead Now</button>
            </div>`;
        return;
    }
    
    workspace.style.display = "flex";
    emptyState.style.display = "none";
    
    // Header summary details
    document.getElementById("edit-prospect-name").textContent = lead.name;
    document.getElementById("edit-prospect-meta").textContent = `${lead.title} at ${lead.company} • ${lead.industry} • Size: ${lead.company_size}`;
    
    const offerBadge = document.getElementById("edit-matched-offer");
    offerBadge.textContent = lead.matched_segment.go4db_offer;
    
    // Accordion analysis details
    document.getElementById("an-icp-fit").textContent = lead.matched_segment.icp_fit;
    document.getElementById("an-branch").textContent = lead.matched_segment.branch_target;
    document.getElementById("an-pain-point").textContent = lead.matched_segment.pain_point;
    document.getElementById("an-usecase").textContent = lead.matched_segment.data_usecase;
    
    // Check if nurture tab is applicable
    const nurtureTab = document.getElementById("tab-seq-nurture");
    if (lead.email_drafts.reply_nurture) {
        nurtureTab.style.display = "block";
    } else {
        nurtureTab.style.display = "none";
        // Reset active tab if we were on nurture and it got hidden
        if (state.activeSeqTab === 'reply_nurture') {
            state.activeSeqTab = 'initial_pitch';
            document.querySelectorAll(".seq-tab").forEach(t => t.classList.remove("active"));
            document.getElementById("tab-seq-pitch").classList.add("active");
        }
    }
    
    // Populate form editor fields
    const draft = lead.email_drafts[state.activeSeqTab];
    if (draft) {
        document.getElementById("draft-subject").value = draft.subject;
        document.getElementById("draft-body").value = draft.body;
    } else {
        document.getElementById("draft-subject").value = "";
        document.getElementById("draft-body").value = "";
    }
}

// Single AI analyze action
window.triggerSingleAnalysis = async function(leadId) {
    const emptyState = document.getElementById("email-editor-empty-state");
    emptyState.innerHTML = `<div class="empty-state py-5"><h4>Analyzing profile and creating personalized pitches...</h4></div>`;
    
    try {
        // Mock a single trigger by modifying status and calling analysis
        const settings = state.settings;
        const res = await fetch("/api/leads/analyze", { method: "POST" });
        if (res.ok) {
            // Poll immediately to show results
            setTimeout(async () => {
                await fetchState();
                selectLeadFromQueue(leadId);
            }, 1500);
        }
    } catch (e) {
        alert("Single analyze failed: " + e);
    }
};

// Setup email editors interactions
function initEmailEditor() {
    // 1. Accordion Toggle
    const accHeader = document.getElementById("btn-toggle-accordion");
    accHeader.addEventListener("click", () => {
        accHeader.classList.toggle("active");
    });
    
    // 2. Sequence Steps selection
    const seqTabs = document.querySelectorAll(".seq-tab");
    seqTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            seqTabs.forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            state.activeSeqTab = tab.getAttribute("data-seq");
            
            // Re-populate text fields
            if (state.selectedLeadId) {
                const lead = state.leads.find(l => l.id === state.selectedLeadId);
                if (lead && lead.email_drafts && lead.email_drafts[state.activeSeqTab]) {
                    document.getElementById("draft-subject").value = lead.email_drafts[state.activeSeqTab].subject;
                    document.getElementById("draft-body").value = lead.email_drafts[state.activeSeqTab].body;
                }
            }
        });
    });
    
    // 3. Save Draft
    const btnSaveDraft = document.getElementById("btn-save-draft");
    btnSaveDraft.addEventListener("click", async () => {
        if (!state.selectedLeadId) return;
        
        btnSaveDraft.disabled = true;
        btnSaveDraft.textContent = "Saving...";
        
        const payload = {
            lead_id: state.selectedLeadId,
            email_type: state.activeSeqTab,
            subject: document.getElementById("draft-subject").value,
            body: document.getElementById("draft-body").value
        };
        
        try {
            const res = await fetch("/api/leads/update-email", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === "success") {
                // Refresh local cache representation
                const lead = state.leads.find(l => l.id === state.selectedLeadId);
                if (lead && lead.email_drafts) {
                    lead.email_drafts[state.activeSeqTab].subject = payload.subject;
                    lead.email_drafts[state.activeSeqTab].body = payload.body;
                }
                alert("Email template draft saved!");
            }
        } catch (e) {
            alert("Failed to save draft changes: " + e);
        } finally {
            btnSaveDraft.disabled = false;
            btnSaveDraft.textContent = "Save Draft Changes";
        }
    });
    
    // 4. Sequence Simulator reply injections
    const btnSimInt = document.getElementById("btn-sim-interested");
    const btnSimUnint = document.getElementById("btn-sim-uninterested");
    const btnSimOoo = document.getElementById("btn-sim-ooo");
    const btnSimWrong = document.getElementById("btn-sim-wrong");
    const btnSimCustom = document.getElementById("btn-sim-custom-reply");
    const customReplyInput = document.getElementById("sim-custom-reply-text");
    
    const injectReply = async (text) => {
        if (!state.selectedLeadId) {
            alert("Select a lead first.");
            return;
        }
        
        try {
            const res = await fetch("/api/campaign/simulate-reply", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    lead_id: state.selectedLeadId,
                    reply_body: text
                })
            });
            const data = await res.json();
            if (data.status === "success") {
                alert(`Injected simulated reply. The agent is analyzing it in the background...`);
                // Poll quickly
                setTimeout(fetchState, 1500);
            }
        } catch (e) {
            alert("Simulation failed: " + e);
        }
    };
    
    btnSimInt.addEventListener("click", () => {
        injectReply("Hi! This sounds like a great list. What is the pricing for the US Tech Buyers Database? Also, can you send over a sample of 20 contacts to inspect? Thanks!");
    });
    
    btnSimUnint.addEventListener("click", () => {
        injectReply("No, we already have our own contact acquisition provider. Please unsubscribe me and stop emailing.");
    });
    
    btnSimOoo.addEventListener("click", () => {
        injectReply("Thank you for your message. I am out of the office on vacation with limited access to email until June 18th. For urgent growth issues, contact my colleague Dave at dave@acme.com.");
    });
    
    btnSimWrong.addEventListener("click", () => {
        injectReply("I am no longer handling lead acquisitions or marketing lists. Please reach out to our Head of Sales, Clara Brown, at clara.brown@acme.com instead.");
    });
    
    btnSimCustom.addEventListener("click", () => {
        const val = customReplyInput.value.trim();
        if (!val) {
            alert("Type a custom response message first.");
            return;
        }
        injectReply(val);
        customReplyInput.value = "";
    });
}

// Dedicated Sessions Dashboard Functions
function initSessionsDashboard() {
    const grid = document.getElementById("sessions-grid");
    if (grid) {
        grid.addEventListener("click", async (e) => {
            const btn = e.target.closest("button");
            
            // If the user clicked a button inside the card
            if (btn) {
                e.stopPropagation(); // Stop event bubbling to card
                
                const campaignId = btn.getAttribute("data-id");
                if (!campaignId) return;
                
                const campaign = state.campaigns.find(c => c.id === campaignId);
                const name = campaign ? campaign.name : "this session";
                
                if (btn.classList.contains("btn-toggle-outreach")) {
                    const isRunning = btn.getAttribute("data-running") === "true";
                    const endpoint = isRunning ? "/api/campaign/pause" : "/api/campaign/start";
                    try {
                        const res = await fetch(`${endpoint}?campaign_id=${campaignId}`, {
                            method: "POST"
                        });
                        if (res.ok) {
                            await fetchState();
                        }
                    } catch (err) {
                        alert("Failed to toggle campaign state: " + err);
                    }
                } else if (btn.classList.contains("btn-delete")) {
                    if (confirm(`Are you sure you want to delete "${name}"? All leads, logs, and drafts for this session will be permanently deleted.`)) {
                        try {
                            const res = await fetch(`/api/campaigns/delete/${campaignId}`, {
                                method: "POST"
                            });
                            if (res.ok) {
                                state.selectedLeadId = null;
                                const workspace = document.getElementById("email-editor-workspace");
                                const emptyState = document.getElementById("email-editor-empty-state");
                                if (workspace) workspace.style.display = "none";
                                if (emptyState) emptyState.style.display = "block";
                                await fetchCampaigns();
                                await fetchState();
                            }
                        } catch (err) {
                            alert("Failed to delete campaign: " + err);
                        }
                    }
                }
                return;
            }
            
            // If the user clicked on the card itself, activate it and go to Overview
            const card = e.target.closest(".session-card");
            if (card) {
                const campaignId = card.getAttribute("data-id");
                if (!campaignId) return;
                
                try {
                    const res = await fetch(`/api/campaigns/active/${campaignId}`, {
                        method: "POST"
                    });
                    if (res.ok) {
                        state.selectedLeadId = null;
                        const workspace = document.getElementById("email-editor-workspace");
                        const emptyState = document.getElementById("email-editor-empty-state");
                        if (workspace) workspace.style.display = "none";
                        if (emptyState) emptyState.style.display = "block";
                        state.activeCampaignId = campaignId;
                        await fetchState();
                        
                        // Navigate to Overview tab automatically
                        const navOverview = document.getElementById("nav-overview");
                        if (navOverview) {
                            navOverview.click();
                        }
                    }
                } catch (err) {
                    alert("Failed to switch campaign: " + err);
                }
            }
        });
    }
}

function renderSessionsPage() {
    const grid = document.getElementById("sessions-grid");
    if (!grid) return;
    
    // Update summary metrics
    const totalSessions = state.campaigns.length;
    const activeSessions = state.campaigns.filter(c => c.is_running).length;
    const totalIngestedLeads = state.campaigns.reduce((sum, c) => sum + (c.size || 0), 0);
    
    const valTotal = document.getElementById("val-total-sessions");
    const valActive = document.getElementById("val-active-sessions");
    const valLeads = document.getElementById("val-total-ingested-leads");
    
    if (valTotal) valTotal.textContent = totalSessions;
    if (valActive) valActive.textContent = activeSessions;
    if (valLeads) valLeads.textContent = totalIngestedLeads;
    
    if (state.campaigns.length === 0) {
        grid.innerHTML = `
            <div class="empty-state py-5 text-center" style="grid-column: 1 / -1; width: 100%;">
                <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="margin: 0 auto 16px auto; display: block; color: var(--text-muted);">
                    <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
                </svg>
                <h4 style="font-family: var(--font-heading); font-weight: 600; color: var(--text-main); margin-bottom: 8px;">No campaign sessions found</h4>
                <p class="text-muted" style="margin-bottom: 20px;">Get started by importing leads or creating a new campaign.</p>
                <button class="btn btn-primary" onclick="document.getElementById('nav-import').click()">+ Create Session</button>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = state.campaigns.map(c => {
        const isActive = (c.id === state.activeCampaignId);
        const isRunning = c.is_running;
        
        let dateStr = "N/A";
        if (c.created_at) {
            try {
                dateStr = new Date(c.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                console.error("Error formatting date:", e);
            }
        }
        
        return `
            <div class="session-card ${isActive ? 'active' : ''}" data-id="${c.id}">
                <div class="session-card-header">
                    <div class="session-card-header-main">
                        <h4 style="margin:0;">${escapeHtml(c.name)}</h4>
                        <span>Created: ${dateStr}</span>
                    </div>
                    <span class="session-status-badge ${isRunning ? 'running' : 'paused'}">
                        ${isRunning ? '● Running' : '⏸ Paused'}
                    </span>
                </div>
                
                <div class="session-card-metrics">
                    <div class="session-metric-item">
                        <div class="session-metric-val">${c.size || 0}</div>
                        <div class="session-metric-lbl">Leads</div>
                    </div>
                    <div class="session-metric-item">
                        <div class="session-metric-val">${c.total_sent || 0}</div>
                        <div class="session-metric-lbl">Sent</div>
                    </div>
                    <div class="session-metric-item">
                        <div class="session-metric-val">${c.total_replies || 0}</div>
                        <div class="session-metric-lbl">Replies</div>
                    </div>
                </div>
                
                <div class="session-card-actions">
                    <button class="btn ${isRunning ? 'btn-secondary' : 'btn-primary'} btn-sm btn-toggle-outreach" data-id="${c.id}" data-running="${isRunning}">
                        ${isRunning ? '⏸ Pause' : '⚡ Start'}
                    </button>
                    
                    <button class="btn btn-secondary btn-sm btn-delete" data-id="${c.id}">
                        <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin-right: 4px; display: inline-block; vertical-align: middle;">
                            <path d="M19 7l-.867 12.142A2 2 0 0 1 16.138 21H7.862a2 2 0 0 1-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16"/>
                        </svg>Delete
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function populateAssigneeFilter() {
    const filterEl = document.getElementById("hot-leads-assignee-filter");
    if (!filterEl) return;
    
    const currentVal = filterEl.value;
    
    const userIds = state.users.map(u => u.id).join(",");
    if (filterEl.dataset.userIds === userIds) return;
    
    filterEl.innerHTML = `
        <option value="all">All Assignees</option>
        <option value="unassigned">Unassigned</option>
        ${state.users.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join("")}
    `;
    
    filterEl.dataset.userIds = userIds;
    filterEl.value = currentVal;
    if (!filterEl.value) filterEl.value = "all";
}

window.assignLead = async function(leadId, userId) {
    try {
        const res = await fetch(`/api/leads/assign/${leadId}`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ assigned_to: userId || null })
        });
        if (res.ok) {
            const lead = state.leads.find(l => l.id === leadId);
            if (lead) lead.assigned_to = userId || null;
            renderHotLeadsTable();
        } else {
            alert("Failed to assign lead: " + (await res.text()));
        }
    } catch (e) {
        alert("Error assigning lead: " + e);
    }
};

function renderHotLeadsTable() {
    const tbody = document.getElementById("hot-leads-table-body");
    const countLabel = document.getElementById("lbl-hot-leads-count");
    if (!tbody) return;
    
    populateAssigneeFilter();
    
    const filterEl = document.getElementById("hot-leads-assignee-filter");
    const filterVal = filterEl ? filterEl.value : "all";
    
    // Filter hot leads (status: Interested)
    const hotLeads = state.leads.filter(l => l.status === "Interested");
    
    let filteredHotLeads = hotLeads;
    if (filterVal === "unassigned") {
        filteredHotLeads = hotLeads.filter(l => !l.assigned_to);
    } else if (filterVal !== "all") {
        filteredHotLeads = hotLeads.filter(l => l.assigned_to === filterVal);
    }
    
    if (countLabel) {
        countLabel.textContent = `${filteredHotLeads.length} Hot Leads Detected`;
    }
    
    if (filteredHotLeads.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="7" class="text-center py-5">
                    <div class="empty-state">
                        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="margin: 0 auto 16px auto; display: block; color: var(--text-muted);">
                            <path d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 9q3 0 3-4c0 0 5 3 5 8a8 8 0 01-.343 3.657zM9.879 16.121A3 3 0 1012.015 11L11 11.5c-1 1-1.5 2-1.121 4.621z"/>
                        </svg>
                        <h4>No hot leads detected</h4>
                        <p class="text-muted">Prospects who reply with positive/interested sentiment will automatically appear here.</p>
                    </div>
                </td>
            </tr>`;
        return;
    }
    
    tbody.innerHTML = filteredHotLeads.map(lead => {
        // Find latest reply content
        let latestReply = "No reply text recorded.";
        if (lead.replies && lead.replies.length > 0) {
            latestReply = lead.replies[lead.replies.length - 1].body;
        } else if (lead.history && lead.history.length > 0) {
            const replies = lead.history.filter(h => h.action && h.action.toLowerCase().includes("reply"));
            if (replies.length > 0) {
                latestReply = replies[replies.length - 1].details || latestReply;
            }
        }
        
        const displayReply = escapeHtml(latestReply).replace(/\n/g, "<br>");
        
        let scoreClass = "";
        if (lead.score >= 80) scoreClass = "high";
        else if (lead.score >= 50) scoreClass = "medium";
        const scoreStr = lead.score > 0 ? lead.score : "-";
        
        const webLink = lead.company_website || (lead.matched_segment ? lead.matched_segment.website : "") || "";
        const formattedWebLink = webLink ? `<a href="${webLink.startsWith('http') ? webLink : 'https://' + webLink}" target="_blank" class="text-primary d-block">${escapeHtml(webLink)}</a>` : '<span class="text-muted">-</span>';
        
        const linkedin = lead.linkedin_url || (lead.matched_segment ? lead.matched_segment.linkedin : "") || "";
        const formattedLinkedin = linkedin ? `<a href="${linkedin.startsWith('http') ? linkedin : 'https://' + linkedin}" target="_blank" class="text-primary d-block">${escapeHtml(linkedin)}</a>` : '<span class="text-muted">-</span>';

        const assigneeOptions = state.users.map(u => 
            `<option value="${u.id}" ${lead.assigned_to === u.id ? 'selected' : ''}>${escapeHtml(u.name)} (${escapeHtml(u.role)})</option>`
        ).join("");
        
        const assigneeSelect = `
            <select class="form-control form-control-sm" onchange="assignLead('${lead.id}', this.value)" style="background: var(--bg-surface-hover); border-color: var(--border-color); color: var(--text-main); font-size: 12px; padding: 4px 8px; border-radius: 4px; width: 140px;">
                <option value="">Unassigned</option>
                ${assigneeOptions}
            </select>
        `;

        return `
            <tr>
                <td>
                    <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(lead.name)}</div>
                    <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(lead.title)} at <strong>${escapeHtml(lead.company)}</strong></div>
                </td>
                <td>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span>${escapeHtml(lead.email)}</span>
                        <button class="btn btn-secondary btn-sm p-1" onclick="navigator.clipboard.writeText('${lead.email}'); alert('Email copied: ${lead.email}')" title="Copy Email">
                            📋
                        </button>
                        <a href="mailto:${lead.email}" class="btn btn-secondary btn-sm p-1" title="Send Direct Email">
                            ✉
                        </a>
                    </div>
                </td>
                <td>
                    <div style="font-size: 12px;">
                        <div>Web: ${formattedWebLink}</div>
                        <div>IN: ${formattedLinkedin}</div>
                    </div>
                </td>
                <td style="max-width: 300px; font-size: 12px; line-height: 1.4; color: var(--text-main);">
                    <div style="max-height: 80px; overflow-y: auto; background: var(--bg-surface-hover); border: 1px solid var(--border-color); border-radius: 4px; padding: 6px 10px;">
                        ${displayReply}
                    </div>
                </td>
                <td>
                    <span class="score-badge ${scoreClass}">${scoreStr}</span>
                </td>
                <td>
                    ${assigneeSelect}
                </td>
                <td>
                    <div style="display: flex; align-items: center; gap: 4px; width: max-content;">
                        <button class="btn btn-primary btn-sm btn-open-editor" onclick="openLeadInEditor('${lead.id}')">
                            ✏ Reply
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Not_Interested', 'Marked Uninterested', 'Marked manually as not interested.')" title="Mark Not Interested">
                            ⏸ Opt-out
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Junk', 'Marked Junk', 'Marked manually as junk / bounce.')" title="Mark Junk">
                            🗑 Junk
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

window.manuallyUpdateLeadStatus = async function(leadId, status, action, details) {
    try {
        const res = await fetch(`/api/leads/set-status/${leadId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status, action, details })
        });
        if (res.ok) {
            await fetchState();
        } else {
            alert("Failed to update status: " + (await res.text()));
        }
    } catch (e) {
        alert("Error updating status: " + e);
    }
};

window.openLeadInEditor = function(leadId) {
    state.selectedLeadId = leadId;
    
    const navBtn = document.getElementById("nav-email-preview");
    if (navBtn) {
        navBtn.click();
    }
};

window.renderRepliesTable = function() {
    const tbody = document.getElementById("replies-table-body");
    const countLabel = document.getElementById("lbl-replies-count");
    if (!tbody) return;
    
    // Filter leads that have replied (status in Replied, Interested, Not_Interested, OOO, Wrong_Contact)
    const repliedLeads = state.leads.filter(l => 
        ["Replied", "Interested", "Not_Interested", "OOO", "Wrong_Contact"].includes(l.status)
    );
    
    if (countLabel) {
        countLabel.textContent = `${repliedLeads.length} Replies Detected`;
    }
    
    if (repliedLeads.length === 0) {
        tbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="5" class="text-center py-5">
                    <div class="empty-state">
                        <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="margin: 0 auto 16px auto; display: block; color: var(--text-muted);">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                        </svg>
                        <h4>No replies detected yet</h4>
                        <p class="text-muted">Replies from prospects will automatically appear here as they are received.</p>
                    </div>
                </td>
            </tr>`;
        return;
    }
    
    tbody.innerHTML = repliedLeads.map(lead => {
        // Find latest reply content
        let latestReply = "No reply text recorded.";
        if (lead.replies && lead.replies.length > 0) {
            latestReply = lead.replies[lead.replies.length - 1].body;
        } else if (lead.history && lead.history.length > 0) {
            const replies = lead.history.filter(h => h.action && h.action.toLowerCase().includes("reply"));
            if (replies.length > 0) {
                latestReply = replies[replies.length - 1].details || latestReply;
            }
        }
        
        const displayReply = escapeHtml(latestReply).replace(/\n/g, "<br>");
        const statusClass = lead.status.toLowerCase();
        
        return `
            <tr>
                <td>
                    <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(lead.name)}</div>
                    <div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(lead.title)} at <strong>${escapeHtml(lead.company)}</strong></div>
                </td>
                <td>
                    <div style="display: flex; flex-direction: column; gap: 4px;">
                        <span>${escapeHtml(lead.email)}</span>
                        <button class="btn btn-secondary btn-mini" onclick="navigator.clipboard.writeText('${lead.email}'); alert('Email copied: ${lead.email}')" title="Copy Email">
                            📋 Copy Email
                        </button>
                    </div>
                </td>
                <td>
                    <span class="status-pill ${statusClass}">${lead.status.replace(/_/g, ' ')}</span>
                </td>
                <td style="max-width: 400px; font-size: 12px; line-height: 1.4; color: var(--text-main);">
                    <div style="max-height: 100px; overflow-y: auto; background: var(--bg-surface-hover); border: 1px solid var(--border-color); border-radius: 4px; padding: 8px 12px; font-family: monospace;">
                        ${displayReply}
                    </div>
                </td>
                <td>
                    <div style="display: flex; flex-direction: column; gap: 4px; width: max-content;">
                        <button class="btn btn-primary btn-sm btn-open-editor" onclick="openLeadInEditor('${lead.id}')">
                            ✏ Reply in Editor
                        </button>
                        <div style="display: flex; gap: 4px;">
                            <button class="btn btn-secondary btn-sm" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Interested', 'Marked Interested', 'Marked manually as interested.')" title="Mark Hot (Interested)" style="border-color: var(--color-success); color: var(--color-success);">
                                🔥 Hot
                            </button>
                            <button class="btn btn-secondary btn-sm" onclick="manuallyUpdateLeadStatus('${lead.id}', 'Not_Interested', 'Marked Uninterested', 'Marked manually as not interested.')" title="Mark Not Interested" style="border-color: #64748b; color: #64748b;">
                                Opt-out
                            </button>
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
};

// Authentication and RBAC Logic

function initAuth() {
    // Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        const token = localStorage.getItem("session_token");
        if (token) {
            if (!options.headers) {
                options.headers = {};
            }
            if (options.headers instanceof Headers) {
                options.headers.set("X-Session-Token", token);
            } else if (Array.isArray(options.headers)) {
                const hasToken = options.headers.some(h => h[0].toLowerCase() === 'x-session-token');
                if (!hasToken) {
                    options.headers.push(["X-Session-Token", token]);
                }
            } else {
                options.headers["X-Session-Token"] = token;
            }
        }
        return originalFetch(url, options).then(response => {
            if (response.status === 401 && !url.includes("/api/auth/login") && !url.includes("/api/auth/me")) {
                localStorage.removeItem("session_token");
                state.currentUser = null;
                showLogin();
            }
            return response;
        });
    };

    checkAuth();
}

function checkAuth() {
    const token = localStorage.getItem("session_token");
    if (!token) {
        showLogin();
    } else {
        fetchCurrentUser(token);
    }
}

async function fetchCurrentUser(token) {
    try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
            state.currentUser = await res.json();
            showApp();
            applyRoleRestrictions();
            
            // Trigger initial fetch since now we are authorized
            fetchSettings().then(() => {
                fetchCampaigns().then(() => {
                    fetchState();
                    if (!pollingIntervalId) {
                        pollingIntervalId = setInterval(fetchState, 3000);
                    }
                });
            });
        } else {
            localStorage.removeItem("session_token");
            showLogin();
        }
    } catch (e) {
        console.error("Error fetching current user:", e);
        localStorage.removeItem("session_token");
        showLogin();
    }
}

function showLogin() {
    document.getElementById("login-overlay").style.display = "flex";
    document.getElementById("app-container").style.display = "none";
    if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
        pollingIntervalId = null;
    }
}

function showApp() {
    document.getElementById("login-overlay").style.display = "none";
    document.getElementById("app-container").style.display = "flex";
}

function applyRoleRestrictions() {
    const role = state.currentUser ? state.currentUser.role : "Sales Rep";
    
    const adminTabs = [
        "nav-sessions",
        "nav-overview",
        "nav-import",
        "nav-leads",
        "nav-replies",
        "nav-email-preview",
        "nav-settings"
    ];
    
    if (role === "Sales Rep") {
        adminTabs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = "none";
        });
        
        const btnReset = document.getElementById("btn-reset-campaign");
        const btnPause = document.getElementById("btn-pause-campaign");
        const btnStart = document.getElementById("btn-start-campaign");
        if (btnReset) btnReset.style.display = "none";
        if (btnPause) btnPause.style.display = "none";
        if (btnStart) btnStart.style.display = "none";
        
        const roleCard = document.getElementById("settings-role-management");
        if (roleCard) roleCard.style.display = "none";
        
        const hotLeadsTab = document.getElementById("nav-hot-leads");
        if (hotLeadsTab) {
            hotLeadsTab.click();
        }
    } else {
        adminTabs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = "flex";
        });
        
        const btnReset = document.getElementById("btn-reset-campaign");
        const btnPause = document.getElementById("btn-pause-campaign");
        const btnStart = document.getElementById("btn-start-campaign");
        if (btnReset) btnReset.style.display = "block";
        if (btnPause) btnPause.style.display = "block";
        if (btnStart) btnStart.style.display = "block";
        
        const roleCard = document.getElementById("settings-role-management");
        if (roleCard) {
            roleCard.style.display = "block";
            renderTeamMembersTable();
        }
    }
}

function renderTeamMembersTable() {
    const tbody = document.getElementById("team-members-tbody");
    if (!tbody) return;
    
    tbody.innerHTML = "";
    
    if (state.users.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center text-muted" style="padding: 20px;">
                    No team members found.
                </td>
            </tr>
        `;
        return;
    }
    
    state.users.forEach(u => {
        const tr = document.createElement("tr");
        
        const nameCell = document.createElement("td");
        nameCell.textContent = u.name;
        tr.appendChild(nameCell);
        
        const usernameCell = document.createElement("td");
        usernameCell.textContent = u.email || u.username;
        tr.appendChild(usernameCell);
        
        const roleCell = document.createElement("td");
        roleCell.textContent = u.role;
        tr.appendChild(roleCell);
        
        const actionsCell = document.createElement("td");
        if (u.id === "admin_user" || u.username === "admin" || u.email === "admin@admin.com") {
            actionsCell.innerHTML = `<span class="text-muted" style="font-size: 11px;">System Admin (Protected)</span>`;
        } else {
            const btnDelete = document.createElement("button");
            btnDelete.className = "btn btn-secondary";
            btnDelete.style.padding = "4px 8px";
            btnDelete.style.fontSize = "11px";
            btnDelete.style.backgroundColor = "#ef4444";
            btnDelete.style.color = "#ffffff";
            btnDelete.style.border = "none";
            btnDelete.style.borderRadius = "4px";
            btnDelete.style.cursor = "pointer";
            btnDelete.textContent = "Delete";
            btnDelete.addEventListener("click", () => deleteTeamMember(u.id, u.name));
            actionsCell.appendChild(btnDelete);
        }
        tr.appendChild(actionsCell);
        
        tbody.appendChild(tr);
    });
}

async function deleteTeamMember(userId, name) {
    if (confirm(`Are you sure you want to delete team member "${name}"?`)) {
        try {
            const res = await fetch(`/api/users/delete/${userId}`, {
                method: "POST"
            });
            if (res.ok) {
                alert("Team member deleted successfully.");
                state.users = state.users.filter(u => u.id !== userId);
                renderTeamMembersTable();
            } else {
                alert("Failed to delete team member: " + (await res.text()));
            }
        } catch (e) {
            alert("Error deleting team member: " + e);
        }
    }
}

function initTeamManagementUI() {
    const btnAdd = document.getElementById("btn-add-team-member");
    if (!btnAdd) return;
    
    btnAdd.addEventListener("click", async () => {
        const nameVal = document.getElementById("team-name").value.trim();
        const userVal = document.getElementById("team-email").value.trim();
        const passVal = document.getElementById("team-password").value;
        const roleVal = document.getElementById("team-role").value;
        
        if (!nameVal || !userVal || !passVal) {
            alert("All fields are required to add a team member.");
            return;
        }
        
        try {
            const res = await fetch("/api/users/add", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: nameVal,
                    email: userVal,
                    password: passVal,
                    role: roleVal
                })
            });
            const data = await res.json();
            if (res.ok) {
                alert("Team member added successfully!");
                document.getElementById("team-name").value = "";
                document.getElementById("team-email").value = "";
                document.getElementById("team-password").value = "";
                
                await fetchState();
                renderTeamMembersTable();
            } else {
                alert("Failed to add team member: " + data.detail);
            }
        } catch (e) {
            alert("Error adding team member: " + e);
        }
    });
}

function initLoginForm() {
    const form = document.getElementById("login-form");
    if (!form) return;
    
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const usernameVal = document.getElementById("login-email").value.trim();
        const passwordVal = document.getElementById("login-password").value;
        const errorMsg = document.getElementById("login-error-msg");
        
        if (errorMsg) errorMsg.style.display = "none";
        
        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: usernameVal, password: passwordVal })
            });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                localStorage.setItem("session_token", data.token);
                state.currentUser = data.user;
                showApp();
                applyRoleRestrictions();
                
                fetchSettings().then(() => {
                    fetchCampaigns().then(() => {
                        fetchState();
                        if (!pollingIntervalId) {
                            pollingIntervalId = setInterval(fetchState, 3000);
                        }
                    });
                });
            } else {
                if (errorMsg) {
                    errorMsg.textContent = data.detail || "Invalid credentials.";
                    errorMsg.style.display = "block";
                }
            }
        } catch (err) {
            if (errorMsg) {
                errorMsg.textContent = "Server communication failure.";
                errorMsg.style.display = "block";
            }
            console.error("Login request error:", err);
        }
    });
}

function initLogoutButton() {
    const btnLogout = document.getElementById("btn-logout-sidebar");
    if (!btnLogout) return;
    
    btnLogout.addEventListener("click", async () => {
        if (confirm("Are you sure you want to log out?")) {
            try {
                await fetch("/api/auth/logout", { method: "POST" });
            } catch (e) {
                console.error("Logout request failed:", e);
            }
            localStorage.removeItem("session_token");
            state.currentUser = null;
            showLogin();
        }
    });
}

