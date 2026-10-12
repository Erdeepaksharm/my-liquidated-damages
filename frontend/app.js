// Contract Compliance & Liquidated Damages Engine - Client Controller

let currentPO = null;
let currentCalculation = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
    initDropzone();
    initApiKey();
});

// --- API Key Management ---
function initApiKey() {
    const key = getStoredApiKey();
    updateApiKeyBadge(!!key);
}

function getStoredApiKey() {
    return localStorage.getItem("GEMINI_API_KEY") || "";
}

function updateApiKeyBadge(isConnected) {
    const btn = document.getElementById("apiKeyBtn");
    if (isConnected) {
        btn.innerHTML = `<span style="color: #059669; font-weight: 800;">●</span> <span>API Active</span>`;
        btn.style.borderColor = "#10b981";
    } else {
        btn.innerHTML = `<span>API Configuration</span>`;
        btn.style.borderColor = "";
    }
}

function openGeminiModal() {
    const modal = document.getElementById("geminiModal");
    const input = document.getElementById("geminiKeyInput");
    input.value = getStoredApiKey();
    modal.style.display = "flex";
    document.getElementById("testKeyFeedback").style.display = "none";
}

function closeGeminiModal() {
    document.getElementById("geminiModal").style.display = "none";
}

function saveGeminiKey() {
    const input = document.getElementById("geminiKeyInput");
    const key = input.value.trim();
    if (key) {
        localStorage.setItem("GEMINI_API_KEY", key);
        updateApiKeyBadge(true);
    } else {
        localStorage.removeItem("GEMINI_API_KEY");
        updateApiKeyBadge(false);
    }
    closeGeminiModal();
}

async function testGeminiConnection() {
    const input = document.getElementById("geminiKeyInput");
    const key = input.value.trim();
    const feedback = document.getElementById("testKeyFeedback");

    if (!key) {
        feedback.style.display = "block";
        feedback.style.background = "#fee2e2";
        feedback.style.color = "#dc2626";
        feedback.textContent = "Please provide an API key.";
        return;
    }

    feedback.style.display = "block";
    feedback.style.background = "#eff6ff";
    feedback.style.color = "#2563eb";
    feedback.textContent = "Validating endpoint connection...";

    try {
        const resp = await fetch("/api/test-gemini-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key })
        });
        const data = await resp.json();
        if (resp.ok && data.valid) {
            feedback.style.background = "#ecfdf5";
            feedback.style.color = "#059669";
            feedback.textContent = "Connection established successfully.";
        } else {
            throw new Error(data.detail || "Authentication error.");
        }
    } catch (err) {
        feedback.style.background = "#fee2e2";
        feedback.style.color = "#dc2626";
        feedback.textContent = `Error: ${err.message}`;
    }
}

// --- Drag & Drop Upload ---
function initDropzone() {
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("poFileInput");

    ["dragenter", "dragover", "dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.add("dragover"));
    });

    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, () => dropzone.classList.remove("dragover"));
    });

    dropzone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });
}

let currentUploadController = null;

async function handleFileUpload(file) {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
        alert("Please select a valid PDF file.");
        return;
    }

    const apiKey = getStoredApiKey();
    if (!apiKey) {
        openGeminiModal();
        const feedback = document.getElementById("testKeyFeedback");
        feedback.style.display = "block";
        feedback.style.background = "#fef3c7";
        feedback.style.color = "#b45309";
        feedback.textContent = "API key required. Please configure and save your API key.";
        return;
    }

    // Display progress
    document.getElementById("dropzone").style.display = "none";
    document.getElementById("loadingOverlay").style.display = "block";
    document.getElementById("resultsArea").style.display = "none";

    const formData = new FormData();
    formData.append("file", file);
    formData.append("gemini_api_key", apiKey);

    // Cancel any previous in-flight upload if user starts a new one
    if (currentUploadController) {
        try { currentUploadController.abort(); } catch (e) {}
    }
    currentUploadController = new AbortController();

    try {
        const response = await fetch("/api/upload-po-pdf", {
            method: "POST",
            body: formData,
            signal: currentUploadController.signal
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: "Processing error occurred." }));
            throw new Error(err.detail || "Document extraction failed.");
        }

        const data = await response.json();
        currentPO = data.extracted_po;
        currentCalculation = data.calculation;

        renderMatrixView(currentPO, currentCalculation);

        // Header status badge
        document.getElementById("fileStatusBadge").style.display = "flex";
        document.getElementById("badgeFileName").textContent = `${file.name}`;

    } catch (error) {
        console.error("Upload error:", error);
        // If aborted by user action or navigation, do not alert
        if (error.name === "AbortError" || (error.message && error.message.toLowerCase().includes("abort"))) {
            console.log("Upload aborted or reset.");
        } else {
            alert(`Error: ${error.message}`);
            resetApp();
        }
    } finally {
        currentUploadController = null;
        document.getElementById("loadingOverlay").style.display = "none";
    }
}

// --- Render Matrix & Console ---
function renderMatrixView(po, calc) {
    document.getElementById("dropzoneContainer").style.display = "none";
    document.getElementById("resultsArea").style.display = "block";

    // 1. Populate Yellow Rows (Captured from document)
    document.getElementById("matrixPoNumber").value = po.po_number || "PO-REF";
    document.getElementById("matrixCurrency").textContent = po.currency || "NGN";
    document.getElementById("matrixPoAmount").value = (po.total_po_value || 0).toFixed(2);
    document.getElementById("matrixLdRate").value = ((po.ld_rate_per_week || 0.01) * 100).toFixed(1);
    document.getElementById("matrixLdCap").value = ((po.max_ld_limit_percent || 0.05) * 100).toFixed(1);

    // 2. Populate Orange Row (Delay Parameter)
    const netDays = calc ? calc.delay_excl_force_majeure_days : 0;
    const netWeeks = calc ? calc.delay_in_weeks : 0;
    document.getElementById("matrixDelayDays").value = netDays;
    document.getElementById("matrixDelayWeeksLabel").textContent = `(${netWeeks.toFixed(2)} Weeks)`;

    // 3. Populate Blue Rows (Calculated Financials)
    updateCalculatedOutputs(calc);

    // 4. Initialize Console
    initConsoleGreeting(po, calc);
}

function updateCalculatedOutputs(calc) {
    if (!calc) return;
    const currency = calc.currency || (currentPO ? currentPO.currency : "NGN");
    document.getElementById("matrixLdAmount").textContent = `${currency} ${calc.calculated_total_ld.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById("matrixNetPayable").textContent = `${currency} ${calc.net_payable_amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    
    const capBadge = document.getElementById("matrixCapBadge");
    if (calc.is_capped) {
        capBadge.textContent = "Statutory Cap Applied";
        capBadge.style.background = "#fee2e2";
        capBadge.style.color = "#b91c1c";
    } else {
        capBadge.textContent = "Standard Rate";
        capBadge.style.background = "#eff6ff";
        capBadge.style.color = "#1d4ed8";
    }
}

// --- Live Input Handlers ---
function handleManualUpdate() {
    if (!currentPO) return;

    currentPO.po_number = document.getElementById("matrixPoNumber").value.trim();
    currentPO.total_po_value = parseFloat(document.getElementById("matrixPoAmount").value) || 0;
    currentPO.invoice_value = currentPO.total_po_value;
    currentPO.ld_rate_per_week = (parseFloat(document.getElementById("matrixLdRate").value) || 1.0) / 100.0;
    currentPO.max_ld_limit_percent = (parseFloat(document.getElementById("matrixLdCap").value) || 5.0) / 100.0;

    const delayDays = parseFloat(document.getElementById("matrixDelayDays").value) || 0;
    recalculateLD(delayDays);
}

function handleDelayInput(delayDaysVal) {
    const delayDays = parseFloat(delayDaysVal) || 0;
    recalculateLD(delayDays);
    
    addChatMessage("user", `Delay set to ${delayDays} days`);
    addChatMessage("agent", `Delay updated to **${delayDays} days** (${(delayDays/7.0).toFixed(2)} weeks). Liquidated Damages recalculation complete.`);
}

function recalculateLD(delayDays) {
    if (!currentPO) return;

    const netWeeks = delayDays / 7.0;
    document.getElementById("matrixDelayWeeksLabel").textContent = `(${netWeeks.toFixed(2)} Weeks)`;

    const totalVal = currentPO.total_po_value || 0;
    const rate = currentPO.ld_rate_per_week || 0.01;
    const capPct = currentPO.max_ld_limit_percent || 0.05;

    const ldPerWeek = totalVal * rate;
    const maxCap = totalVal * capPct;
    let calculatedLD = ldPerWeek * netWeeks;
    let isCapped = false;

    if (calculatedLD > maxCap) {
        calculatedLD = maxCap;
        isCapped = true;
    }

    calculatedLD = Math.round(calculatedLD * 100) / 100;
    const netPayable = Math.round((totalVal - calculatedLD) * 100) / 100;

    currentCalculation = {
        po_number: currentPO.po_number,
        currency: currentPO.currency,
        total_po_value: totalVal,
        invoice_value: totalVal,
        delay_in_days: delayDays,
        delay_excl_force_majeure_days: delayDays,
        delay_in_weeks: netWeeks,
        completed_delayed_weeks: netWeeks,
        ld_rate_per_week: rate,
        max_ld_limit_percent: capPct,
        ld_per_completed_week: ldPerWeek,
        calculated_total_ld: calculatedLD,
        max_allowable_ld: maxCap,
        is_capped: isCapped,
        net_payable_amount: netPayable
    };

    updateCalculatedOutputs(currentCalculation);
}

// --- Console Chat System ---
function initConsoleGreeting(po, calc) {
    const chatContainer = document.getElementById("chatMessages");
    chatContainer.innerHTML = "";

    const currency = po.currency || "NGN";
    const amountStr = (po.total_po_value || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const rateStr = `${((po.ld_rate_per_week || 0.01) * 100).toFixed(2)}% per week`;
    const capStr = `${((po.max_ld_limit_percent || 0.05) * 100).toFixed(2)}%`;

    const greetingHTML = `
        <div style="font-weight: 700; color: #0f172a; margin-bottom: 8px;">
            Document Terms Extracted:
        </div>
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 12px; font-size: 0.88rem; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
            <div><span style="color: #64748b;">Contract Ref:</span> <strong>${po.po_number}</strong></div>
            <div><span style="color: #64748b;">Contract Value:</span> <strong>${currency} ${amountStr}</strong></div>
            <div><span style="color: #64748b;">Clause 6 Rate:</span> <strong>${rateStr}</strong></div>
            <div><span style="color: #64748b;">Maximum Cap:</span> <strong>${capStr}</strong></div>
        </div>
        <div style="color: #1e293b; font-weight: 600; font-size: 0.92rem;">
            Specify the delivery delay in days or weeks to execute the Liquidated Damages calculation.
        </div>
    `;

    addChatMessage("agent", greetingHTML, true);
}

function addChatMessage(sender, content, isHTML = false) {
    const container = document.getElementById("chatMessages");
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender === 'agent' ? 'chat-bubble-agent' : 'chat-bubble-user'}`;
    
    if (isHTML) {
        bubble.innerHTML = content;
    } else {
        // Professional formatted markdown rendering
        let formatted = content
            .replace(/###\s*(.*)/g, '<div style="font-size: 1rem; font-weight: 700; color: #0f172a; margin-bottom: 8px;">$1</div>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.88rem;">$1</code>')
            .replace(/\n\n/g, '<div style="height: 8px;"></div>')
            .replace(/\n/g, '<br>');
        bubble.innerHTML = formatted;
    }
    
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

function sendQuickMessage(text) {
    document.getElementById("chatInput").value = text;
    sendMessage();
}

async function sendMessage() {
    const input = document.getElementById("chatInput");
    const msg = input.value.trim();
    if (!msg) return;

    addChatMessage("user", msg);
    input.value = "";

    if (!currentPO) {
        addChatMessage("agent", "Please upload a purchase order document to proceed with assessment.");
        return;
    }

    const apiKey = getStoredApiKey();

    try {
        const resp = await fetch("/api/chat-assistant", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: msg,
                po: currentPO,
                gemini_api_key: apiKey
            })
        });

        if (resp.ok) {
            const data = await resp.json();
            currentPO = data.po;
            currentCalculation = data.calculation;

            // Synchronize Table State
            document.getElementById("matrixDelayDays").value = data.delay_days;
            document.getElementById("matrixDelayWeeksLabel").textContent = `(${data.delay_weeks.toFixed(2)} Weeks)`;
            document.getElementById("matrixLdRate").value = ((currentPO.ld_rate_per_week || 0.01) * 100).toFixed(1);
            document.getElementById("matrixLdCap").value = ((currentPO.max_ld_limit_percent || 0.05) * 100).toFixed(1);
            
            updateCalculatedOutputs(currentCalculation);
            addChatMessage("agent", data.reply);
        } else {
            handleLocalCalculation(msg);
        }
    } catch (err) {
        handleLocalCalculation(msg);
    }
}

function handleLocalCalculation(msg) {
    const msgLower = msg.toLowerCase();
    let days = 0;
    
    const mWks = msgLower.match(/(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b/);
    if (mWks) {
        days = parseFloat(mWks[1]) * 7.0;
    } else {
        const mDays = msgLower.match(/(\d+(?:\.\d+)?)\s*(?:days?|d)\b/);
        if (mDays) {
            days = parseFloat(mDays[1]);
        } else {
            const mNum = msgLower.match(/\b(\d+(?:\.\d+)?)\b/);
            if (mNum) days = parseFloat(mNum[1]);
        }
    }

    if (days > 0) {
        document.getElementById("matrixDelayDays").value = days;
        recalculateLD(days);
        const weeks = (days / 7.0).toFixed(2);
        const currency = currentPO.currency || "NGN";
        const ldStr = currentCalculation.calculated_total_ld.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const netStr = currentCalculation.net_payable_amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        
        addChatMessage("agent", `
            <strong>Assessment Calculation:</strong><br>
            • Net Delay: ${days} days (${weeks} weeks)<br>
            • Assessed Liquidated Damages: <strong>${currency} ${ldStr}</strong><br>
            • Net Payable to Supplier: <strong>${currency} ${netStr}</strong>
        `);
    } else {
        addChatMessage("agent", "Please provide the delivery delay duration (e.g. '10 days' or '2 weeks') to calculate Liquidated Damages.");
    }
}

// --- Export Handlers ---
async function exportExcel() {
    if (!currentPO || !currentCalculation) {
        alert("No active calculation available.");
        return;
    }

    try {
        const resp = await fetch("/api/export-excel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ po: currentPO, calculation: currentCalculation })
        });
        if (!resp.ok) throw new Error("Spreadsheet export failed.");
        
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `LD_Calculation_${currentPO.po_number.replace(/[^A-Za-z0-9]/g, '_')}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (err) {
        alert(`Export error: ${err.message}`);
    }
}

async function exportPDF() {
    if (!currentPO || !currentCalculation) {
        alert("No active calculation available.");
        return;
    }

    try {
        const resp = await fetch("/api/export-pdf", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ po: currentPO, calculation: currentCalculation })
        });
        if (!resp.ok) throw new Error("PDF export failed.");
        
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `LD_Annexure_${currentPO.po_number.replace(/[^A-Za-z0-9]/g, '_')}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (err) {
        alert(`Export error: ${err.message}`);
    }
}

function resetApp() {
    if (currentUploadController) {
        try { currentUploadController.abort(); } catch (e) {}
        currentUploadController = null;
    }
    currentPO = null;
    currentCalculation = null;
    document.getElementById("dropzoneContainer").style.display = "block";
    document.getElementById("dropzone").style.display = "block";
    document.getElementById("loadingOverlay").style.display = "none";
    document.getElementById("resultsArea").style.display = "none";
    document.getElementById("fileStatusBadge").style.display = "none";
    document.getElementById("poFileInput").value = "";
}
