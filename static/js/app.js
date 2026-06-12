document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // DOM Elements
    const btnStart = document.getElementById("btn-start");
    const btnStop = document.getElementById("btn-stop");
    const headerPulse = document.getElementById("header-pulse");
    const headerStatusText = document.getElementById("header-status-text");
    const statEngine = document.getElementById("stat-engine");
    const statGesture = document.getElementById("stat-gesture");
    const volumeVal = document.getElementById("volume-val");
    const volumeBarInner = document.getElementById("volume-bar-inner");
    const logsList = document.getElementById("logs-list");
    const logsCount = document.getElementById("logs-count");
    const mappingsContainer = document.getElementById("mappings-container");
    const mappingsForm = document.getElementById("mappings-form");
    const btnResetMappings = document.getElementById("btn-reset-mappings");

    let isRunning = false;
    let pollInterval = null;
    let existingLogsCount = 0;

    // Default Action labels cache
    let actionLabels = {};

    // Helper to automatically bypass ngrok warning page on API requests
    async function customFetch(url, options = {}) {
        if (!options.headers) {
            options.headers = {};
        }
        options.headers["ngrok-skip-browser-warning"] = "true";
        return fetch(url, options);
    }

    // 1. Load Custom Mappings and populate the form
    async function loadMappings() {
        try {
            const res = await customFetch("/api/mappings");
            const data = await res.json();
            
            actionLabels = data.labels;
            renderMappings(data.mappings, data.labels);
        } catch (err) {
            console.error("Error loading mappings:", err);
            mappingsContainer.innerHTML = `<div class="mapping-loading" style="color: var(--color-red);">Error loading settings.</div>`;
        }
    }

    function renderMappings(mappings, labels) {
        mappingsContainer.innerHTML = "";
        
        // Loop through gesture keys
        Object.entries(mappings).forEach(([gesture, currentAction]) => {
            const row = document.createElement("div");
            row.className = "mapping-row";
            
            // Format labels for UI (replace underscores with spaces)
            const formattedGesture = gesture.replace("_", " ");
            
            let optionsHTML = "";
            Object.entries(labels).forEach(([actionKey, actionLabel]) => {
                const selected = actionKey === currentAction ? "selected" : "";
                optionsHTML += `<option value="${actionKey}" ${selected}>${actionLabel}</option>`;
            });

            row.innerHTML = `
                <label>
                    <i data-lucide="hand"></i> ${formattedGesture}
                </label>
                <select name="${gesture}">
                    ${optionsHTML}
                </select>
            `;
            
            mappingsContainer.appendChild(row);
        });
        
        // Re-run lucide to draw icons on dynamically added elements
        lucide.createIcons();
    }

    // Submit Mappings form
    mappingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const formData = new FormData(mappingsForm);
        const newMappings = {};
        
        formData.forEach((value, key) => {
            newMappings[key] = value;
        });

        try {
            const res = await customFetch("/api/mappings", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(newMappings)
            });
            const data = await res.json();
            if (data.success) {
                showTemporaryMessage("Mappings updated successfully!", "success");
            }
        } catch (err) {
            console.error("Error updating mappings:", err);
            showTemporaryMessage("Failed to update mappings.", "error");
        }
    });

    // Reset Mappings to original state
    btnResetMappings.addEventListener("click", () => {
        const defaults = {
            "fist": "mute",
            "peace": "play_pause",
            "point_up": "volume_up",
            "open_palm": "volume_down",
            "thumbs_up": "next_slide",
            "thumbs_down": "prev_slide"
        };
        renderMappings(defaults, actionLabels);
    });

    // 2. Controller Action controls (Start/Stop)
    btnStart.addEventListener("click", async () => {
        btnStart.classList.add("btn-disabled");
        btnStart.disabled = true;
        
        try {
            const res = await customFetch("/api/start", { method: "POST" });
            const data = await res.json();
            
            if (data.success) {
                updateEngineUI(true);
                startPolling();
            } else {
                alert(data.message);
                btnStart.classList.remove("btn-disabled");
                btnStart.disabled = false;
            }
        } catch (err) {
            console.error("Error starting controller:", err);
            btnStart.classList.remove("btn-disabled");
            btnStart.disabled = false;
        }
    });

    btnStop.addEventListener("click", async () => {
        btnStop.classList.add("btn-disabled");
        btnStop.disabled = true;
        
        try {
            const res = await customFetch("/api/stop", { method: "POST" });
            const data = await res.json();
            
            if (data.success) {
                updateEngineUI(false);
                stopPolling();
                // Refresh img element to show the standby offline picture
                const streamImg = document.getElementById("video-stream");
                streamImg.src = "/video_feed?t=" + new Date().getTime();
            }
        } catch (err) {
            console.error("Error stopping controller:", err);
            btnStop.classList.remove("btn-disabled");
            btnStop.disabled = false;
        }
    });

    function updateEngineUI(running) {
        isRunning = running;
        if (running) {
            btnStart.disabled = true;
            btnStart.classList.add("btn-disabled");
            btnStop.disabled = false;
            btnStop.classList.remove("btn-disabled");
            
            headerPulse.classList.add("running");
            headerStatusText.textContent = "RUNNING";
            headerStatusText.style.color = "var(--color-green)";
            
            statEngine.textContent = "RUNNING";
            statEngine.style.color = "var(--color-green)";
        } else {
            btnStart.disabled = false;
            btnStart.classList.remove("btn-disabled");
            btnStop.disabled = true;
            btnStop.classList.add("btn-disabled");
            
            headerPulse.classList.remove("running");
            headerStatusText.textContent = "OFFLINE";
            headerStatusText.style.color = "var(--color-red)";
            
            statEngine.textContent = "OFFLINE";
            statEngine.style.color = "var(--color-red)";
            statGesture.textContent = "NONE";
        }
    }

    // 3. Status Polling and Logs
    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        
        // Initial call
        pollStatus();
        pollLogs();
        
        // Loop every 500ms
        pollInterval = setInterval(() => {
            pollStatus();
            pollLogs();
        }, 500);
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
        // Run one last log update to fetch final shutdown log
        setTimeout(pollLogs, 300);
    }

    async function pollStatus() {
        try {
            const res = await customFetch("/api/status");
            const data = await res.json();
            
            // Sync engine state just in case it crashes or closes out-of-band
            if (data.running !== isRunning) {
                updateEngineUI(data.running);
            }
            
            if (data.running) {
                // Update active gesture
                statGesture.textContent = data.active_gesture.toUpperCase().replace("_", " ");
                statGesture.style.color = data.active_gesture !== "None" ? "var(--color-cyan)" : "var(--text-main)";
            }
            
            // Sync system volume level UI
            volumeVal.textContent = `${data.volume}%`;
            volumeBarInner.style.width = `${data.volume}%`;
            
        } catch (err) {
            console.error("Error polling status:", err);
        }
    }
 
    async function pollLogs() {
        try {
            const res = await customFetch("/api/logs");
            const data = await res.json();
            
            const logs = data.logs;
            logsCount.textContent = `${logs.length} Actions`;
            
            if (logs.length === 0) {
                logsList.innerHTML = `<div class="log-placeholder">System waiting for gesture triggers...</div>`;
                existingLogsCount = 0;
                return;
            }
            
            // Render logs in reverse order (newest first)
            let logsHTML = "";
            [...logs].reverse().forEach(log => {
                let logTypeClass = "";
                if (log.action === "System") logTypeClass = "system";
                else if (log.action.includes("Volume") || log.action.includes("Mute") || log.action.includes("Play") || log.action.includes("Slide")) {
                    logTypeClass = "success";
                }
                
                logsHTML += `
                    <div class="log-item ${logTypeClass}">
                        <span class="log-time">${log.time}</span>
                        <span class="log-action">${log.action}</span>
                        <span class="log-detail">${log.detail}</span>
                    </div>
                `;
            });
            
            logsList.innerHTML = logsHTML;
            existingLogsCount = logs.length;
            
        } catch (err) {
            console.error("Error polling logs:", err);
        }
    }

    // Helper to display temporary action message/toast
    function showTemporaryMessage(message, type) {
        const toast = document.createElement("div");
        toast.className = "toast-message";
        toast.style.position = "fixed";
        toast.style.bottom = "2rem";
        toast.style.right = "2rem";
        toast.style.background = type === "success" ? "linear-gradient(135deg, var(--color-green), var(--color-indigo))" : "var(--color-red)";
        toast.style.color = type === "success" ? "#060913" : "white";
        toast.style.padding = "0.75rem 1.5rem";
        toast.style.borderRadius = "8px";
        toast.style.fontWeight = "600";
        toast.style.boxShadow = "0 8px 24px rgba(0,0,0,0.3)";
        toast.style.zIndex = "1000";
        toast.style.animation = "log-slide-in 0.3s ease-out";
        toast.textContent = message;

        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transition = "opacity 0.5s ease";
            setTimeout(() => toast.remove(), 500);
        }, 2500);
    }

    // Initialize mappings
    loadMappings();
    // Poll logs immediately on start to show any system state
    pollLogs();
    pollStatus();
});
