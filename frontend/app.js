let currentUser = null;
let selectedSemester = null;
let activePeerId = null;

// ==========================================
// API Fetch Wrapper
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

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>'"]/g, tag => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[tag] || tag));
}

// ==========================================
// Initialization
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  const storedUser = localStorage.getItem('auth_token');
  
  // Load public quest catalogue & matrix immediately so page is never blank
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
  currentUser = { username: username, role: username.toLowerCase() === 'ganshyam' ? 'creator' : 'member' };
  document.getElementById('auth-status-label').innerText = `ACTIVE: ${username.toUpperCase()} [${currentUser.role.toUpperCase()}]`;
  document.getElementById('profile-name-role').innerText = `${username.toUpperCase()} [${currentUser.role.toUpperCase()}]`;

  await Promise.all([
    loadQuests(),
    loadGuildMatrix(),
    loadPeers(),
    checkDeadlines()
  ]);
}

function logout() {
  localStorage.removeItem('auth_token');
  location.reload();
}

// ==========================================
// Auth Handlers (Enforced Member Only)
// ==========================================
function switchAuthTab(tab) {
  const loginView = document.getElementById('auth-login-view');
  const regView = document.getElementById('auth-register-view');
  const loginBtn = document.getElementById('tab-login-btn');
  const regBtn = document.getElementById('tab-register-btn');

  if (tab === 'login') {
    loginView.style.display = 'block';
    regView.style.display = 'none';
    loginBtn.className = 'pixel-btn';
    regBtn.className = 'pixel-btn sem-tab';
  } else {
    loginView.style.display = 'none';
    regView.style.display = 'block';
    regBtn.className = 'pixel-btn';
    loginBtn.className = 'pixel-btn sem-tab';
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
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Authentication failed');

    localStorage.setItem('auth_token', data.user.username);
    document.getElementById('auth-modal').style.display = 'none';
    await initSession(data.user.username);
  } catch (err) {
    alert(err.message);
  }
}

async function submitRegister() {
  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;
  const sem = parseInt(document.getElementById('reg-sem').value, 10);

  if (!username) return alert('Enter a callsign.');
  if (password.length < 4) return alert('Passphrase must be at least 4 characters.');

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, current_semester: sem })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Registration failed');

    alert(`Unit initialized for ${data.user.username}. Logged in.`);
    localStorage.setItem('auth_token', data.user.username);
    document.getElementById('auth-modal').style.display = 'none';
    await initSession(data.user.username);
  } catch (err) {
    alert(err.message);
  }
}

// ==========================================
// Quest Log & Hackerrank Locks
// ==========================================
function switchSemesterTab(sem) {
  selectedSemester = sem;
  loadQuests();
}

async function loadQuests() {
  try {
    const url = selectedSemester ? `/api/quests?semester=${selectedSemester}` : '/api/quests';
    const res = await apiFetch(url);
    if (!res.ok) return;
    const data = await res.json();

    const activeSem = data.current_active_semester || 3;
    selectedSemester = data.selected_semester || activeSem;
    const quests = data.quests || [];

    document.getElementById('quest-log-heading').innerText = 
      `SEMESTER ${selectedSemester} QUEST LOG ${selectedSemester === activeSem ? '[CURRENT CADENCE]' : ''}`;

    document.querySelectorAll('.sem-tab').forEach(btn => {
      btn.classList.toggle('active', btn.innerText === `SEM ${selectedSemester}`);
    });

    const listContainer = document.getElementById('quest-list-container');
    listContainer.innerHTML = '';
    document.getElementById('quest-count').innerText = `${quests.length} QUESTS`;

    if (quests.length === 0) {
      listContainer.innerHTML = `<div style="padding: 12px; color: #64748b; font-size: 11px;">No milestones assigned for Semester ${selectedSemester}.</div>`;
      return;
    }

    quests.forEach(q => {
      const isDone = q.status === 'COMPLETED' || q.status === 'SUBMITTED';
      const isLocked = q.status === 'LOCKED';

      let dateColor = '#cbd5e1';
      let dateText = `${q.start_date || 'TBD'} → ${q.end_date || 'TBD'}`;
      if (!isDone && !isLocked && q.days_remaining !== undefined) {
        if (q.days_remaining < 0) {
          dateColor = 'var(--text-red)';
          dateText = `OVERDUE BY ${Math.abs(q.days_remaining)} DAYS`;
        } else if (q.days_remaining <= 3) {
          dateColor = 'var(--text-red)';
          dateText = `DUE IN ${q.days_remaining} DAYS`;
        }
      }

      const aiPrompt = `Act as an expert software engineering mentor. I am working on an engineering quest titled '${q.title}'. The tech stack involves: ${q.tech_stack || 'General Engineering'}. Here is the brief: ${q.description}. Please break this down into actionable implementation steps and guide me on where to start.`;

      const questEl = document.createElement('div');
      questEl.className = `quest-item ${isLocked ? 'locked' : ''}`;

      questEl.innerHTML = `
        <div class="quest-header-row" onclick="${isLocked ? '' : `toggleDetails(${q.id})`}">
          <div style="max-width: 68%;">
            <div style="margin-bottom: 2px;">
              ${q.tier === 'major' ? '<span class="badge badge-boss">MAJOR BOSS</span>' : ''}
              <strong style="color: var(--text-gold); font-size: 11px;">${q.code}:</strong> 
              <span style="font-weight: 600;">${q.title}</span>
            </div>
            <div style="font-size: 10px; margin-top: 3px;">
              <span style="color: ${dateColor}; font-weight: ${q.days_remaining <= 3 && !isDone && !isLocked ? 'bold' : 'normal'}">${dateText}</span> • 
              <span style="color: var(--text-cyan);">+${q.xp_reward || 100} XP</span>
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="badge ${isDone ? 'badge-done' : (isLocked ? 'badge-locked' : '')}">${q.status}</span>
            <button class="pixel-btn" style="padding: 2px 8px; font-size: 10px;" 
                    onclick="event.stopPropagation(); openQuestModal(${q.id}, '${escapeHtml(q.title)}')"
                    ${isLocked ? 'disabled' : ''}>
              ${isDone ? 'RESUBMIT' : 'SUBMIT'}
            </button>
          </div>
        </div>

        <div id="details-${q.id}" class="quest-details-pane">
          <div style="color: var(--text-cyan); margin-bottom: 4px;"><strong>TECH STACK / SKILLS:</strong> ${q.tech_stack || 'Standard Stack'}</div>
          <div style="color: #94a3b8; margin-bottom: 10px; line-height: 1.4;"><strong>BRIEF:</strong> ${q.description || 'No description provided.'}</div>
          <button class="pixel-btn" onclick="copyAiPrompt('${escapeHtml(aiPrompt)}', event)">
            🤖 COPY AI MENTOR PROMPT
          </button>
        </div>
      `;
      listContainer.appendChild(questEl);
    });
  } catch (err) {
    console.error('Failed to load quests:', err);
  }
}

function toggleDetails(id) {
  const el = document.getElementById(`details-${id}`);
  if (el) el.style.display = el.style.display === 'block' ? 'none' : 'block';
}

function copyAiPrompt(promptText, ev) {
  if (ev) ev.stopPropagation();
  navigator.clipboard.writeText(promptText).then(() => {
    alert('AI Mentor prompt copied to clipboard!');
  });
}

function openQuestModal(id, title) {
  if (!localStorage.getItem('auth_token')) {
    document.getElementById('auth-modal').style.display = 'flex';
    return;
  }
  document.getElementById('submit-quest-id').value = id;
  document.getElementById('submit-modal-title').innerText = `SUBMIT: ${title}`;
  document.getElementById('submit-repo-url').value = '';
  document.getElementById('submit-notes').value = '';
  document.getElementById('submit-modal').style.display = 'flex';
}

function closeSubmitModal() {
  document.getElementById('submit-modal').style.display = 'none';
}

async function submitQuestForm() {
  const questId = parseInt(document.getElementById('submit-quest-id').value, 10);
  const repoUrl = document.getElementById('submit-repo-url').value;
  const notes = document.getElementById('submit-notes').value;

  try {
    const res = await apiFetch('/api/quests/submit', {
      method: 'POST',
      body: JSON.stringify({ quest_id: questId, submission_url: repoUrl, notes: notes })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Submission failed');

    alert(result.message);
    closeSubmitModal();
    await loadQuests();
    await loadGuildMatrix();
  } catch (err) {
    alert(err.message);
  }
}

// ==========================================
// Guild VASAVI Roster
// ==========================================
async function loadGuildMatrix() {
  try {
    const res = await fetch('/api/team/progress');
    if (!res.ok) return;
    const team = await res.json();
    const container = document.getElementById('guild-roster-container');
    container.innerHTML = '';

    if (team.length === 0) {
      container.innerHTML = `<div style="color: #64748b; font-size: 11px;">No registered guild members.</div>`;
      return;
    }

    team.forEach((member, index) => {
      const isHead = index === 0;
      const row = document.createElement('div');
      row.className = `guild-row ${isHead ? 'guild-head-anim' : ''}`;

      row.innerHTML = `
        <div>
          <strong style="color: ${isHead ? 'var(--text-gold)' : 'inherit'};">${member.username.toUpperCase()}</strong> 
          <span style="font-size: 10px; color: #64748b;">[${member.role.toUpperCase()}]</span>
        </div>
        ${isHead ? '<span class="guild-head-tag">👑 GUILD HEAD</span>' : ''}
        <span class="badge badge-done">XP: ${member.xp || 0}</span>
      `;
      container.appendChild(row);

      if (currentUser && member.username.toLowerCase() === currentUser.username.toLowerCase()) {
        const xp = member.xp || 0;
        document.getElementById('profile-level').innerText = `LVL ${Math.max(1, Math.floor(xp / 100))}`;
        document.getElementById('profile-xp-bar').style.width = `${Math.min(100, (xp % 100))}%`;
      }
    });
  } catch (err) {
    console.error('Failed to load Guild matrix:', err);
  }
}

// ==========================================
// Alerts & Comms
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
    if (peers.length === 0) {
      container.innerHTML = `<div style="color: #64748b; font-size: 10px; padding: 6px;">No external peers.</div>`;
      return;
    }

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

    if (msgs.length === 0) {
      log.innerHTML = `<div style="color: #64748b; margin: auto;">No transmissions exchanged yet.</div>`;
      return;
    }

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

function openBioModal() {
  alert('Biometric scanner calibrated.');
}