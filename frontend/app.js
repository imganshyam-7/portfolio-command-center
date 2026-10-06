let currentSelectedQuestId = null;
let currentExpectedSlug = "";

document.addEventListener("DOMContentLoaded", () => {
    refreshGameHUD();
});

async function refreshGameHUD() {
    await loadPlayerStats();
    await loadFreezeStatus();
    await loadQuests();
}

async function loadPlayerStats() {
    try {
        const res = await fetch("/api/player");
        const player = await res.json();

        document.getElementById("player-title").innerText = `${player.player_name.toUpperCase()} [${player.rank_title.toUpperCase()}]`;
        document.getElementById("level-badge").innerText = `LVL 0${player.current_semester} (SEM ${player.current_semester})`;
        
        document.getElementById("hp-text").innerText = `${player.hp}/${player.max_hp}`;
        const hpPct = Math.round((player.hp / player.max_hp) * 100);
        document.getElementById("hp-fill").style.width = `${hpPct}%`;

        document.getElementById("xp-text").innerText = `${player.current_xp}/${player.xp_to_next_level}`;
        const xpPct = Math.min(100, Math.round((player.current_xp / player.xp_to_next_level) * 100));
        document.getElementById("xp-fill").style.width = `${xpPct}%`;
    } catch (err) {
        console.error("Error loading player stats", err);
    }
}

async function loadFreezeStatus() {
    try {
        const res = await fetch("/api/freeze-status");
        const data = await res.json();

        const pill = document.getElementById("freeze-flag");
        const pillText = document.getElementById("freeze-pill-text");
        const countdown = document.getElementById("countdown-days");

        if (data.is_frozen) {
            pill.className = "freeze-pill frozen";
            pillText.innerText = `FREEZE ACTIVE: ${data.active_event}`;
            countdown.innerText = "0";
        } else {
            pill.className = "freeze-pill normal";
            pillText.innerText = "PROTOCOL: STANDBY (BUILD PHASE)";
            countdown.innerText = data.days_to_next_freeze ?? "--";
        }
    } catch (err) {
        console.error("Error loading freeze status", err);
    }
}

async function loadQuests() {
    try {
        const res = await fetch("/api/quests");
        const quests = await res.json();

        document.getElementById("quest-count").innerText = `${quests.length} QUESTS`;
        const container = document.getElementById("quests-container");
        container.innerHTML = "";

        quests.forEach(q => {
            const div = document.createElement("div");
            const isCompleted = q.status === "COMPLETED";
            const isActive = q.is_active_today;

            div.className = `quest-item ${isActive ? "ongoing-active" : ""} ${isCompleted ? "completed" : ""}`;
            div.innerHTML = `
                <div class="quest-info">
                    <div class="quest-header-line">
                        <span class="quest-type-tag">${q.cadence_type}</span>
                        <span class="polish-tag" style="color: ${q.polish_tag.includes('🎯') ? 'var(--text-gold)' : '#94a3b8'}">${q.polish_tag}</span>
                        ${isActive ? '<span class="ongoing-tag">ONGOING NOW</span>' : ''}
                        <span class="quest-title">${q.title}</span>
                    </div>
                    <div class="quest-submeta">
                        <span>DOMAIN: ${q.domain}</span>
                        <span>POD: ${q.assigned_pod}</span>
                        <span>DUE: ${q.deadline}</span>
                        <span>REWARD: +${q.base_xp} XP</span>
                    </div>
                </div>
                <div>
                    ${
                        isCompleted
                        ? `<button class="pixel-btn completed-btn" disabled>RESOLVED ✓</button>`
                        : `<button class="pixel-btn done-btn" onclick="openQuestModal(${q.id}, '${q.title}', '${q.required_repo_name}')">CLAIM / DONE</button>`
                    }
                </div>
            `;
            container.appendChild(div);
        });
    } catch (err) {
        console.error("Error loading quests", err);
    }
}

function openQuestModal(id, title, slug) {
    currentSelectedQuestId = id;
    currentExpectedSlug = slug;

    document.getElementById("modal-quest-title").innerText = title;
    document.getElementById("modal-expected-slug").innerText = slug;
    document.getElementById("repo-url-input").value = "";
    document.getElementById("modal-error").className = "modal-error hidden";
    document.getElementById("quest-modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("quest-modal").classList.add("hidden");
    currentSelectedQuestId = null;
    currentExpectedSlug = "";
}

async function confirmQuestSubmission() {
    const repoUrl = document.getElementById("repo-url-input").value.trim();
    const errorBox = document.getElementById("modal-error");

    if (!repoUrl) {
        errorBox.innerText = "Please enter a valid Git Repository URL.";
        errorBox.classList.remove("hidden");
        return;
    }

    if (!repoUrl.toLowerCase().includes(currentExpectedSlug.toLowerCase())) {
        errorBox.innerText = `Invalid Repo! Expected URL to contain '${currentExpectedSlug}'.`;
        errorBox.classList.remove("hidden");
        return;
    }

    try {
        const res = await fetch(`/api/quests/${currentSelectedQuestId}/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repo_url: repoUrl })
        });

        const data = await res.json();
        if (!res.ok) {
            errorBox.innerText = data.detail || "Submission rejected by system.";
            errorBox.classList.remove("hidden");
            return;
        }

        alert(data.message + (data.leveled_up ? "\n\n🎉 LEVEL UP! PROMOTED TO NEXT SEMESTER!" : ""));
        closeModal();
        refreshGameHUD();
    } catch (err) {
        errorBox.innerText = "Network error communicating with server.";
        errorBox.classList.remove("hidden");
    }
}