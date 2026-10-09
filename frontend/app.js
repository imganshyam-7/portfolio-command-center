let currentUser = null;
let selectedSemester = 3;
let activePeerId = null;
let currentSpotlightQuest = null;
let activeQuestsCatalog = [];
let pendingWelcomeUser = null;

let activeStreams = {};

async function startCamera(videoElementId) {
  try {
    if (activeStreams[videoElementId]) {
      stopCamera(videoElementId);
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 320, height: 240, facingMode: 'user' }
    });
    const videoEl = document.getElementById(videoElementId);
    if (videoEl) {
      videoEl.srcObject = stream;
      activeStreams[videoElementId] = stream;
      await videoEl.play().catch(() => {});
    }
  } catch (err) {
    console.error("Camera access error:", err);
    alert("Camera permission denied. Facial verification requires active webcam access.");
  }
}

function stopCamera(videoElementId) {
  if (activeStreams[videoElementId]) {
    activeStreams[videoElementId].getTracks().forEach(track => track.stop());
    delete activeStreams[videoElementId];
  }
  const videoEl = document.getElementById(videoElementId);
  if (videoEl) videoEl.srcObject = null;
}

function captureFrame(videoElementId) {
  const video = document.getElementById(videoElementId);
  if (!video || !video.videoWidth || video.videoWidth === 0) {
    throw new Error("Camera feed initializing. Please wait a moment and face the sensor directly.");
  }
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.85);
}

// ==========================================
// Safe API Fetch Helper (Prevents "Unexpected token 'I'")
// ==========================================
async function apiFetch(endpoint, options = {}) {
  const token = localStorage.getItem('auth_token') || '';
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {})
  };
  
  const res = await fetch(endpoint, { ...options, headers });
  if (res.status === 401 && !endpoint.includes('/api/auth/')) {
    localStorage.removeItem('auth_token');
    document.getElementById('auth-modal').style.display = 'flex';
  }
  return res;
}

async function parseJsonResponse(res) {
  const rawText = await res.text();
  let parsed;
  try {
    parsed = JSON.parse(rawText);
  } catch (err) {
    throw new Error(`Server returned status ${res.status}: ${rawText || 'Internal Server Error'}`);
  }
  if (!res.ok) {
    throw new Error(parsed.detail || parsed.message || 'Operation failed');
  }
  return parsed;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>'"]/g, tag => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[tag] || tag));
}

// ==========================================
// Dynamic RPG Level Scaling
// Level L -> L+1 requires (L * 100) XP
// ==========================================
function getRpgStats(totalXp) {
  let xp = Math.max(0, parseInt(totalXp, 10) || 0);
  let level = 1;
  let accumulated = 0;

  while (true) {
    const requiredForCurrentLevel = level * 100;
    if (xp < accumulated + requiredForCurrentLevel) {
      const xpInLevel = xp - accumulated;
      const progressPercent = Math.min(100, Math.max(0, Math.round((xpInLevel / requiredForCurrentLevel) * 100)));
      return {
        level,
        totalXp: xp,
        xpInLevel,
        requiredForCurrentLevel,
        progressPercent,
        xpRemaining: requiredForCurrentLevel - xpInLevel
      };
    }
    accumulated += requiredForCurrentLevel;
    level++;
  }
}

// ==========================================
// Lifecycle & Auth
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  const storedUser = localStorage.getItem('auth_token');
  await loadQuests();
  await loadGuildMatrix();

  if (!storedUser) {
    document.getElementById('auth-status-label').innerText = 'UNAUTHENTICATED (GUEST)';
    document.getElementById('auth-modal').style.display = 'flex';
  } else {
    await initSession(storedUser);
  }
});

async function initSession(username) {
  const isCreator = username.toLowerCase() === 'ganshyam';
  currentUser = { username: username, role: isCreator ? 'creator' : 'member' };
  
  document.getElementById('auth-status-label').innerText = `ACTIVE: ${username.toUpperCase()} [${currentUser.role.toUpperCase()}]`;
  document.getElementById('profile-name-role').innerText = `${username.toUpperCase()} [${currentUser.role.toUpperCase()}]`;

  const calBtn = document.getElementById('creator-calibrate-btn');
  if (calBtn) calBtn.style.display = isCreator ? 'inline-block' : 'none';

  await checkBiometricStatus();

  await Promise.all([
    loadQuests(),
    loadGuildMatrix(),
    loadPeers(),
    checkDeadlines()
  ]);
}

async function checkBiometricStatus() {
  if (!currentUser || currentUser.role !== 'creator') return;
  try {
    const res = await apiFetch('/api/users');
    if (!res.ok) return;
    const users = await res.json();
    const me = users.find(u => u.username.toLowerCase() === currentUser.username.toLowerCase());
    
    const banner = document.getElementById('bio-warning-banner');
    if (me && !me.has_bio) {
      banner.style.display = 'block';
    } else {
      banner.style.display = 'none';
    }
  } catch (err) {}
}

function logout() {
  localStorage.removeItem('auth_token');
  location.reload();
}

function switchAuthTab(tab) {
  const loginView = document.getElementById('auth-login-view');
  const regView = document.getElementById('auth-register-view');
  const loginBtn = document.getElementById('tab-login-btn');
  const regBtn = document.getElementById('tab-register-btn');

  if (tab === 'login') {
    stopCamera('reg-camera');
    loginView.style.display = 'block';
    regView.style.display = 'none';
    loginBtn.className = 'pixel-btn';
    regBtn.className = 'pixel-btn sem-tab';
  } else {
    loginView.style.display = 'none';
    regView.style.display = 'block';
    regBtn.className = 'pixel-btn';
    loginBtn.className = 'pixel-btn sem-tab';
    startCamera('reg-camera');
  }
}

async function submitLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  if (!username || !password) return alert('Enter callsign and passphrase.');

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await parseJsonResponse(res);

    localStorage.setItem('auth_token', data.user.username);
    document.getElementById('auth-modal').style.display = 'none';
    await initSession(data.user.username);

    if (!data.user.has_biometrics && data.user.role === 'creator') {
      openCalibrationModal();
    }
  } catch (err) {
    alert(err.message);
  }
}

async function submitRegister() {
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;

  if (!username) return alert('Enter a callsign.');
  if (password.length < 4) return alert('Passphrase must be at least 4 characters.');

  let faceImage = "";
  try {
    faceImage = captureFrame('reg-camera');
  } catch (err) {
    return alert(err.message);
  }

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, biometric_image: faceImage })
    });
    const data = await parseJsonResponse(res);

    stopCamera('reg-camera');
    document.getElementById('auth-modal').style.display = 'none';
    showRegistrationCelebration(data.user.username);
  } catch (err) {
    alert(err.message);
  }
}

function showRegistrationCelebration(username) {
  pendingWelcomeUser = username;
  const modal = document.getElementById('bonus-modal');
  if (modal) modal.style.display = 'flex';
}

async function claimBonusAndEnter() {
  const modal = document.getElementById('bonus-modal');
  if (modal) modal.style.display = 'none';
  if (pendingWelcomeUser) {
    localStorage.setItem('auth_token', pendingWelcomeUser);
    await initSession(pendingWelcomeUser);
    pendingWelcomeUser = null;
  }
}

// ==========================================
// Quests & Spotlight Directive
// ==========================================
function switchSemesterTab(sem) {
  selectedSemester = sem;
  loadQuests();
}

async function loadQuests() {
  try {
    const res = await apiFetch(`/api/quests?semester=${selectedSemester}`);
    if (!res.ok) return;
    const data = await res.json();

    const isLocked = data.semester_locked;
    activeQuestsCatalog = data.quests || [];
    currentSpotlightQuest = data.active_quest;

    document.getElementById('quest-log-heading').innerText = `SEMESTER ${selectedSemester} ACTIVE DIRECTIVES`;
    document.querySelectorAll('.sem-tab').forEach(btn => {
      btn.classList.toggle('active', btn.innerText === `SEM ${selectedSemester}`);
    });

    document.getElementById('locked-sem-msg').style.display = isLocked ? 'block' : 'none';

    // Spotlight Box
    const spotlightBox = document.getElementById('active-directive-box');
    if (!isLocked && currentSpotlightQuest) {
      spotlightBox.style.display = 'block';
      document.getElementById('spotlight-title').innerText = `${currentSpotlightQuest.code}: ${currentSpotlightQuest.title}`;
      document.getElementById('spotlight-desc').innerText = currentSpotlightQuest.description;
      document.getElementById('spotlight-stack').innerText = `STACK: ${currentSpotlightQuest.tech_stack || 'Standard'}`;
      document.getElementById('spotlight-xp').innerText = `+${currentSpotlightQuest.xp_reward || 100} XP`;
      
      let dateText = `DEADLINE: ${currentSpotlightQuest.end_date || 'TBD'}`;
      if (currentSpotlightQuest.days_remaining !== undefined) {
        if (currentSpotlightQuest.days_remaining < 0) dateText = `OVERDUE BY ${Math.abs(currentSpotlightQuest.days_remaining)} DAYS`;
        else if (currentSpotlightQuest.days_remaining <= 3) dateText = `DUE IN ${currentSpotlightQuest.days_remaining} DAYS`;
      }
      document.getElementById('spotlight-deadline').innerText = dateText;
    } else {
      spotlightBox.style.display = 'none';
    }

    const listContainer = document.getElementById('quest-list-container');
    listContainer.innerHTML = '';
    document.getElementById('quest-count').innerText = `${activeQuestsCatalog.length} DIRECTIVES`;

    activeQuestsCatalog.forEach(q => {
      const isDone = q.status === 'COMPLETED' || q.status === 'SUBMITTED';
      const isQuesLocked = q.status === 'LOCKED';

      const questEl = document.createElement('div');
      questEl.className = `quest-item ${isQuesLocked ? 'locked' : ''}`;

      questEl.innerHTML = `
        <div class="quest-header-row">
          <div style="max-width: 75%;">
            <span style="font-weight: bold; color: var(--text-gold); font-size: 11px;">${q.code}:</span>
            <span style="font-weight: 600;">${q.title}</span>
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">
              [${q.start_date || 'TBD'} → ${q.end_date || 'TBD'}] • <span style="color: var(--text-cyan);">+${q.xp_reward || 100} XP</span>
            </div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="badge ${isDone ? 'badge-done' : (isQuesLocked ? 'badge-locked' : '')}">${q.status}</span>
            <button class="pixel-btn" style="padding: 3px 8px; font-size: 10px;" 
                    onclick="openQuestModalById(${q.id})"
                    ${isQuesLocked ? 'disabled' : ''}>
              ${isDone ? 'RESUBMIT' : 'SUBMIT'}
            </button>
          </div>
        </div>
      `;
      listContainer.appendChild(questEl);
    });
  } catch (err) {
    console.error('Failed to load quests:', err);
  }
}

function copyActiveMasterPrompt() {
  if (!currentSpotlightQuest) return;
  const q = currentSpotlightQuest;
  const masterPrompt = `Act as an expert senior staff engineer and ECE mentor. I am implementing the following technical milestone:

Title: ${q.title} (${q.code})
Semester: Semester ${q.semester}
Tech Stack / Tools: ${q.tech_stack || 'Standard Embedded/Software Stack'}
Milestone Directive:
${q.description}

Deadline Window: ${q.start_date || 'N/A'} through ${q.end_date || 'N/A'}

Provide a comprehensive, high-tier technical breakdown:
1. Architectural design decisions, protocols, and interface diagrams.
2. Step-by-step implementation roadmap with core algorithms and starter code.
3. Common bugs, edge-cases, and timing pitfalls.
4. Concrete test verification procedures to guarantee production stability.`;

  navigator.clipboard.writeText(masterPrompt).then(() => {
    alert("🤖 AI Master Prompt copied to clipboard!");
  });
}

function openActiveQuestModal() {
  if (!currentSpotlightQuest) return;
  openQuestModalById(currentSpotlightQuest.id);
}

function openQuestModalById(id) {
  if (!localStorage.getItem('auth_token')) {
    document.getElementById('auth-modal').style.display = 'flex';
    return;
  }
  const quest = activeQuestsCatalog.find(q => q.id === id) || currentSpotlightQuest;
  const title = quest ? quest.title : `Directive #${id}`;

  document.getElementById('submit-quest-id').value = id;
  document.getElementById('submit-modal-title').innerText = `SUBMIT: ${title}`;
  document.getElementById('submit-repo-url').value = '';
  document.getElementById('submit-confirm-btn').disabled = false;
  document.getElementById('submit-confirm-btn').innerText = 'AUTHENTICATE & VERIFY';
  document.getElementById('submit-modal').style.display = 'flex';
  
  startCamera('submit-camera');
}

function closeSubmitModal() {
  stopCamera('submit-camera');
  document.getElementById('submit-modal').style.display = 'none';
}

async function submitQuestForm() {
  const questId = parseInt(document.getElementById('submit-quest-id').value, 10);
  const repoUrl = document.getElementById('submit-repo-url').value.trim();
  const btn = document.getElementById('submit-confirm-btn');

  if (!repoUrl) return alert('Enter a valid repository or artifact URL.');

  let snapshot = "";
  try {
    snapshot = captureFrame('submit-camera');
  } catch (err) {
    return alert(err.message);
  }

  btn.disabled = true;
  btn.innerText = 'SCANNING & VERIFYING...';

  try {
    const res = await apiFetch('/api/quests/submit', {
      method: 'POST',
      body: JSON.stringify({
        quest_id: questId,
        submission_url: repoUrl,
        biometric_snapshot: snapshot
      })
    });
    const result = await parseJsonResponse(res);

    alert(result.message);
    closeSubmitModal();
    await loadQuests();
    await loadGuildMatrix();
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.innerText = 'AUTHENTICATE & VERIFY';
  }
}

// ==========================================
// Guild Matrix & RPG Level Sync
// ==========================================
async function loadGuildMatrix() {
  try {
    const res = await fetch('/api/team/progress');
    if (!res.ok) return;
    const team = await res.json();
    
    // Update the live registered counter badge
    const countBadge = document.getElementById('guild-count');
    if (countBadge) countBadge.innerText = `${team.length} REGISTERED`;

    const container = document.getElementById('guild-roster-container');
    container.innerHTML = '';

    team.forEach((member, index) => {
      const isHead = index === 0;
      const stats = getRpgStats(member.xp || 0);
      const row = document.createElement('div');
      row.className = `guild-row ${isHead ? 'guild-head-anim' : ''}`;

            // Admin Delete Button (Only visible to Creator, cannot delete self)
      let adminControls = '';
      if (currentUser && currentUser.role === 'creator' && member.username.toLowerCase() !== 'ganshyam') {
        adminControls = `<button class="pixel-btn btn-danger" style="padding: 2px 5px; font-size: 9px; margin-left: 6px;" title="Remove Cadet" onclick="removeCadet('${member.username}')">X</button>`;
      }

      row.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; max-width: 65%;">
          <strong style="color: ${isHead ? 'var(--text-gold)' : 'inherit'};">${member.username.toUpperCase()}</strong> 
          <span style="font-size: 10px; color: #64748b;">[${member.role.toUpperCase()}]</span>
          ${isHead ? '<span class="guild-head-badge">👑 GUILD HEAD</span>' : ''}
        </div>
        <div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">
          <span class="badge" style="border-color: var(--text-cyan); color: var(--text-cyan);">LVL ${String(stats.level).padStart(2, '0')}</span>
          <span class="badge badge-done">${stats.totalXp} XP</span>
          ${adminControls}
        </div>
      `;

      container.appendChild(row);

      // Active user level & progress bar sync
      if (currentUser && member.username.toLowerCase() === currentUser.username.toLowerCase()) {
        document.getElementById('profile-level').innerText = 
          `LVL ${String(stats.level).padStart(2, '0')} • ${stats.xpInLevel} / ${stats.requiredForCurrentLevel} XP (${stats.progressPercent}%)`;
        document.getElementById('profile-xp-bar').style.width = `${stats.progressPercent}%`;
        document.getElementById('profile-xp-cur').innerText = `TOTAL ACCUMULATED: ${stats.totalXp} XP`;
        document.getElementById('profile-xp-next').innerText = `${stats.xpRemaining} XP NEEDED FOR LVL ${String(stats.level + 1).padStart(2, '0')}`;
      }
    });
  } catch (err) {
    console.error('Failed to load Guild matrix:', err);
  }
}


// ==========================================
// Creator Biometric Enrollment Modal
// ==========================================
function openCalibrationModal() {
  document.getElementById('calibration-modal').style.display = 'flex';
  document.getElementById('cal-save-btn').disabled = false;
  document.getElementById('cal-save-btn').innerText = 'ENROLL MASTER FACE';
  startCamera('calibration-camera');
}

function closeCalibrationModal() {
  stopCamera('calibration-camera');
  document.getElementById('calibration-modal').style.display = 'none';
}

async function executeCalibration() {
  const btn = document.getElementById('cal-save-btn');
  let faceImage = "";
  try {
    faceImage = captureFrame('calibration-camera');
  } catch (err) {
    return alert(err.message);
  }

  btn.disabled = true;
  btn.innerText = 'EXTRACTING 128-D EMBEDDINGS...';

  try {
    const res = await apiFetch('/api/bio/calibrate', {
      method: 'POST',
      body: JSON.stringify({ biometric_image: faceImage })
    });
    const data = await parseJsonResponse(res);

    alert(data.message);
    document.getElementById('bio-warning-banner').style.display = 'none';
    closeCalibrationModal();
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.innerText = 'ENROLL MASTER FACE';
  }
}

// ==========================================
// Alerts & Encrypted Comms
// ==========================================
async function checkDeadlines() {
  try {
    const res = await apiFetch('/api/alerts');
    if (!res.ok) return;
    const data = await res.json();
    if (data.alerts && data.alerts.length > 0) {
      document.getElementById('alert-content').innerHTML = data.alerts.join('<br><br>');
      document.getElementById('alert-modal').style.display = 'flex';
    }
  } catch (err) {
    console.error('Alerts error:', err);
  }
}

function closeAlertModal() {
  document.getElementById('alert-modal').style.display = 'none';
}

async function loadPeers() {
  try {
    const res = await apiFetch('/api/users');
    if (!res.ok) return;
    const users = await res.json();
    const container = document.getElementById('peer-list-container');
    container.innerHTML = '';

    const peers = users.filter(u => !currentUser || u.username.toLowerCase() !== currentUser.username.toLowerCase());
    peers.forEach(peer => {
      const card = document.createElement('div');
      card.className = `peer-card ${activePeerId === peer.id ? 'active' : ''}`;
      card.innerHTML = `<span>${peer.username}</span><span class="badge" style="font-size: 8px;">${peer.role}</span>`;
      card.onclick = () => selectPeer(peer);
      container.appendChild(card);
    });
  } catch (err) {
    console.error('Error loading peers:', err);
  }
}

function selectPeer(peer) {
  activePeerId = peer.id;
  document.getElementById('active-peer-label').innerText = `SECURE LINK: ${peer.username.toUpperCase()}`;
  loadPeers();
  loadTransmissions();
}

async function loadTransmissions() {
  if (!activePeerId) return;
  try {
    const res = await apiFetch(`/api/messages?peer_id=${activePeerId}`);
    if (!res.ok) return;
    const msgs = await res.json();
    const log = document.getElementById('transmission-log');
    log.innerHTML = '';

    msgs.forEach(m => {
      const row = document.createElement('div');
      const isMe = m.sender_name.toLowerCase() === (currentUser ? currentUser.username.toLowerCase() : '');
      row.style.alignSelf = isMe ? 'flex-end' : 'flex-start';
      row.style.maxWidth = '80%';
      row.innerHTML = `
        <span style="color: ${isMe ? 'var(--text-cyan)' : 'var(--text-purple)'}; font-size: 9px;">
          ${escapeHtml(m.sender_name || (isMe ? 'YOU' : 'PEER'))} [${m.timestamp || ''}]
        </span>
        <div style="background: rgba(255,255,255,0.05); padding: 5px 8px; border-radius: 2px; margin-top: 2px;">
          ${escapeHtml(m.content)}
        </div>
      `;
      log.appendChild(row);
    });
    log.scrollTop = log.scrollHeight;
  } catch (err) {
    console.error('Failed to load transmissions:', err);
  }
}

async function sendTransmission() {
  if (!activePeerId) return alert('Select a peer to transmit to.');
  const input = document.getElementById('comms-input');
  const text = input.value.trim();
  if (!text) return;

  try {
    const res = await apiFetch('/api/messages', {
      method: 'POST',
      body: JSON.stringify({ receiver_id: activePeerId, content: text })
    });
    if (res.ok) {
      input.value = '';
      loadTransmissions();
    }
  } catch (err) {
    console.error('Error sending message:', err);
  }
}

// ==========================================
// Admin Controls
// ==========================================
async function removeCadet(targetUsername) {
  const confirmWipe = confirm(`⚠️ WARNING: Are you sure you want to permanently delete cadet [${targetUsername.toUpperCase()}]? This wipes all their XP, quests, and biometrics. This cannot be undone.`);
  
  if (!confirmWipe) return;

  try {
    const res = await apiFetch(`/api/users/${targetUsername}`, { method: 'DELETE' });
    const data = await parseJsonResponse(res);
    
    alert(data.message);
    
    // Refresh the UI to show the user is gone
    await loadGuildMatrix();
    await loadPeers();
  } catch (err) {
    alert(err.message);
  }
}
