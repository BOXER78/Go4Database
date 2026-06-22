document.addEventListener("DOMContentLoaded", () => {
    // State
    let authorsList = {};
    let selectedAuthorKey = "samantha_bansil";
    let generatedData = null;
    let sitemapUrlsCount = 0;

    // Elements
    const form = document.getElementById("generator-form");
    const authorGroup = document.getElementById("author-select-group");
    const sitemapCountEl = document.getElementById("sitemap-count");
    const progressContainer = document.getElementById("progress-container");
    const progressStatusText = document.getElementById("progress-status-text");
    const progressPercentage = document.getElementById("progress-percentage");
    const progressBar = document.getElementById("progress-bar");
    const emptyState = document.getElementById("empty-state");
    const viewerContainer = document.getElementById("viewer-container");
    
    const previewTab = document.getElementById("preview-tab");
    const htmlTab = document.getElementById("html-tab");
    const rawHtmlContent = document.getElementById("raw-html-content");
    const tabButtons = document.querySelectorAll(".tab-btn");
    
    const copyBtn = document.getElementById("copy-btn");
    const downloadBtn = document.getElementById("download-btn");
    const generateBtn = document.getElementById("generate-btn");
    
    const complianceRatio = document.getElementById("compliance-ratio");
    const seoScoreCircle = document.getElementById("seo-score-circle");
    const seoScoreText = document.getElementById("seo-score-text");
    const aiScoreCircle = document.getElementById("ai-score-circle");
    const aiScoreText = document.getElementById("ai-score-text");
    const aiScoreSubtext = document.getElementById("ai-score-subtext");
    const checklistList = document.getElementById("seo-checklist-list");

    // Initialize Lucide Icons
    lucide.createIcons();

    // Fetch Sitemap
    async function loadSitemapInfo() {
        try {
            const res = await fetch("/api/sitemap");
            const data = await res.json();
            sitemapUrlsCount = data.count || 0;
            sitemapCountEl.innerText = `Sitemap: ${sitemapUrlsCount} URLs parsed`;
        } catch (err) {
            console.error("Error loading sitemap", err);
            sitemapCountEl.innerText = "Sitemap: go4database sitemap (Cached)";
        }
    }

    // Fetch Authors
    async function loadAuthors() {
        try {
            const res = await fetch("/api/authors");
            authorsList = await res.json();
            
            authorGroup.innerHTML = "";
            Object.keys(authorsList).forEach((key, index) => {
                const author = authorsList[key];
                const card = document.createElement("div");
                card.className = `author-card ${key === selectedAuthorKey ? "selected" : ""}`;
                card.dataset.key = key;
                
                // Get initials
                const initials = author.name.split(" ").map(n => n[0]).join("");
                
                card.innerHTML = `
                    <div class="author-avatar">${initials}</div>
                    <div class="author-info">
                        <h4>${author.name}</h4>
                        <p>${author.title}</p>
                    </div>
                `;
                
                card.addEventListener("click", () => {
                    document.querySelectorAll(".author-card").forEach(c => c.classList.remove("selected"));
                    card.classList.add("selected");
                    selectedAuthorKey = key;
                });
                
                authorGroup.appendChild(card);
            });
        } catch (err) {
            console.error("Error loading authors", err);
        }
    }

    // Tab Switching
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            const tabId = btn.dataset.tab;
            if (tabId === "preview-tab") {
                previewTab.classList.remove("hidden");
                htmlTab.classList.add("hidden");
            } else {
                previewTab.classList.add("hidden");
                htmlTab.classList.remove("hidden");
            }
        });
    });

    // Form Submit (Generation pipeline)
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const topic = document.getElementById("topic").value;
        const primaryKeyword = document.getElementById("primary_keyword").value;
        const targetWordCount = parseInt(document.getElementById("target_word_count").value) || 1200;
        const customGuidelines = document.getElementById("custom_guidelines").value;
        const intent = document.getElementById("intent").value;
        const faqCount = parseInt(document.getElementById("faq_count").value) || 4;
        const caseStudyRequired = document.getElementById("case_study_required").value;
        const expertOpinionRequired = document.getElementById("expert_opinion_required").value;

        // Reset UI
        emptyState.classList.add("hidden");
        viewerContainer.classList.add("hidden");
        progressContainer.classList.remove("hidden");
        generateBtn.disabled = true;
        
        // Active pipeline steps styles helper
        const setStepActive = (stepNum) => {
            document.querySelectorAll(".pipeline-steps .step").forEach((step, idx) => {
                step.classList.remove("active", "completed");
                if (idx + 1 < stepNum) {
                    step.classList.add("completed");
                } else if (idx + 1 === stepNum) {
                    step.classList.add("active");
                }
            });
        };

        // Fake progress intervals mapping (Gemini resolves synchronously)
        let progressVal = 0;
        let activeStep = 1;
        setStepActive(1);
        
        const progressTimer = setInterval(() => {
            if (progressVal < 90) {
                progressVal += 1;
                progressBar.style.width = `${progressVal}%`;
                progressPercentage.innerText = `${progressVal}%`;
                
                // Map values to step statuses
                if (progressVal < 15) {
                    activeStep = 1;
                    progressStatusText.innerText = "Parsing sitemap & context mapping...";
                    setStepActive(1);
                } else if (progressVal >= 15 && progressVal < 40) {
                    activeStep = 2;
                    progressStatusText.innerText = "Structuring Outlines & SOP validations...";
                    setStepActive(2);
                } else if (progressVal >= 40 && progressVal < 70) {
                    activeStep = 3;
                    progressStatusText.innerText = `Drafting B2B content as ${authorsList[selectedAuthorKey].name}...`;
                    setStepActive(3);
                } else if (progressVal >= 70 && progressVal < 88) {
                    activeStep = 4;
                    progressStatusText.innerText = "Running humanization models & reducing AI signature score...";
                    setStepActive(4);
                } else {
                    activeStep = 5;
                    progressStatusText.innerText = "Running SEO validations & post-generation audits...";
                    setStepActive(5);
                }
            }
        }, 300);

        try {
            const response = await fetch("/api/generate", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    topic,
                    primary_keyword: primaryKeyword,
                    author: selectedAuthorKey,
                    target_word_count: targetWordCount,
                    custom_guidelines: customGuidelines,
                    intent,
                    faq_count: faqCount,
                    case_study_required: caseStudyRequired,
                    expert_opinion_required: expertOpinionRequired
                })
            });

            if (!response.ok) {
                throw new Error("Generation pipeline failed. Please check backend logs.");
            }

            const data = await response.json();
            generatedData = data;
            
            // Finish progress
            clearInterval(progressTimer);
            progressBar.style.width = "100%";
            progressPercentage.innerText = "100%";
            progressStatusText.innerText = "Completed successfully!";
            document.querySelectorAll(".pipeline-steps .step").forEach(s => s.classList.add("completed"));

            setTimeout(() => {
                progressContainer.classList.add("hidden");
                viewerContainer.classList.remove("hidden");
                generateBtn.disabled = false;
                renderOutput();
            }, 600);

        } catch (err) {
            clearInterval(progressTimer);
            progressContainer.classList.add("hidden");
            generateBtn.disabled = false;
            alert(err.message);
        }
    });

    // Render Output content & checklist
    function renderOutput() {
        if (!generatedData) return;

        const { html, metadata, report } = generatedData;

        // Render stylized preview
        // Note: We wrap the HTML inside a Google Doc paper layout container
        previewTab.innerHTML = `
            <div style="background: #eef3fc; border: 1px solid #c3ecff; padding: 12px; border-radius: 6px; font-size: 13px; margin-bottom: 20px; font-family: 'Inter', sans-serif;">
                <div style="margin-bottom: 6px;"><strong>Meta Title (Under 60 chars):</strong> <span style="color:#0b57d0; font-weight: 500;">${metadata.title_tag}</span></div>
                <div><strong>Meta Description (Under 160 chars):</strong> <span style="color:#3c4043;">${metadata.meta_description}</span></div>
            </div>
            <h1>${metadata.title_tag || 'Generated Blog'}</h1>
            <div style="font-size: 13px; color: #666; margin-bottom: 20px; font-style: italic;">
                <strong>Author:</strong> ${authorsList[selectedAuthorKey].name} &bull; 
                <strong>Slug:</strong> /blog/${metadata.url_slug}
            </div>
            ${html}
        `;

        // Update the DOCX link to avoid caching
        const docxBtn = document.getElementById("download-docx-btn");
        if (docxBtn) {
            docxBtn.setAttribute("href", `/static/generated_blog.docx?t=${new Date().getTime()}`);
        }

        // Render code preview
        rawHtmlContent.innerText = `<!-- SEO Meta Tags -->\n<title>${metadata.title_tag}</title>\n<meta name="description" content="${metadata.meta_description}">\n\n<!-- Blog Content -->\n${html}`;

        // Render circular score meters
        let seoScore = 0;
        let displayAiScore = 20;

        try {
            seoScore = (report && typeof report.score_percentage === "number") ? report.score_percentage : 0;
        } catch (e) {
            console.error("Error parsing SEO score", e);
        }

        try {
            if (report && report.checks && report.checks.ai_score_check && report.checks.ai_score_check[1]) {
                const feedbackText = report.checks.ai_score_check[1];
                const match = feedbackText.match(/\d+(\.\d+)?/);
                if (match) {
                    displayAiScore = Math.round(parseFloat(match[0]));
                }
            }
        } catch (e) {
            console.error("Error parsing AI score", e);
        }

        // Circular dash calculation
        // stroke-dasharray = val, 100
        seoScoreCircle.setAttribute("stroke-dasharray", `${seoScore}, 100`);
        seoScoreText.textContent = `${seoScore}%`;

        aiScoreCircle.setAttribute("stroke-dasharray", `${displayAiScore}, 100`);
        aiScoreText.textContent = `${displayAiScore}%`;
        
        // Update AI color based on target threshold (<20% is target)
        if (displayAiScore < 20) {
            aiScoreCircle.parentElement.classList.remove("purple");
            aiScoreCircle.parentElement.classList.add("green");
            aiScoreSubtext.innerText = "Target met (< 20%)";
            aiScoreSubtext.style.color = "var(--accent-green)";
        } else {
            aiScoreCircle.parentElement.classList.remove("green");
            aiScoreCircle.parentElement.classList.add("purple");
            aiScoreSubtext.innerText = "Refine tone to lower score";
            aiScoreSubtext.style.color = "var(--text-muted)";
        }

        // Render checklist list
        checklistList.innerHTML = "";
        let passed = 0;
        let total = 0;

        const friendlyChecknames = {
            "url_slug": "Unique SEO Friendly URL Slug",
            "title_tag": "Meta Title Length (< 60 chars)",
            "meta_description": "Meta Description Length (< 160 chars)",
            "definition_p": "Definition Snippet (40-60 words)",
            "h1_tag": "Single H1 Tag Presence",
            "headings_hierarchy": "Heading Hierarchy (H1 → H2 → H3 → H4)",
            "question_subheadings": "Question-based PAA Headings",
            "toc_anchors": "Jump-linked Table of Contents",
            "keyword_placements": "Keyword presence in H1/H2/Intro/Alt text",
            "faqs_conciseness": "3-5 FAQs with answers under 25 words",
            "comparison_table": "Comparison Table insertion",
            "bolding_density": "Key Terms bolding",
            "tldr_check": "TL;DR with go4database mention",
            "internal_links": "Internal links with SOP Anchors",
            "external_links": "Min 8 Authority outbound links",
            "cta_count": "Exactly 4 B2B CTA links",
            "banner_image": "Banner image with Alt text",
            "ai_score_check": "Humanized tone AI score check"
        };

        Object.keys(report.checks).forEach(key => {
            const check = report.checks[key];
            const isPassed = check[0];
            const feedback = check[1];
            
            total++;
            if (isPassed) passed++;

            const item = document.createElement("li");
            item.className = `checklist-item ${isPassed ? "passed" : "failed"}`;
            
            item.innerHTML = `
                <i data-lucide="${isPassed ? 'check-circle' : 'x-circle'}" class="checklist-icon"></i>
                <div class="checklist-info">
                    <h4>${friendlyChecknames[key] || key}</h4>
                    <p>${feedback}</p>
                </div>
            `;
            checklistList.appendChild(item);
        });

        complianceRatio.innerText = `${passed} of ${total} rules met (${Math.round((passed/total)*100)}%)`;
        lucide.createIcons();
    }

    // Action: Copy HTML
    copyBtn.addEventListener("click", () => {
        if (!generatedData) return;
        const text = rawHtmlContent.innerText;
        navigator.clipboard.writeText(text).then(() => {
            copyBtn.innerHTML = `<i data-lucide="check"></i> Copied!`;
            lucide.createIcons();
            setTimeout(() => {
                copyBtn.innerHTML = `<i data-lucide="copy"></i> Copy Code`;
                lucide.createIcons();
            }, 2000);
        });
    });

    // Action: Download HTML
    downloadBtn.addEventListener("click", () => {
        if (!generatedData) return;
        const text = rawHtmlContent.innerText;
        const blob = new Blob([text], { type: "text/html" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${generatedData.metadata.url_slug || 'blog'}.html`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    // Run startup loads
    loadSitemapInfo();
    loadAuthors();
});
