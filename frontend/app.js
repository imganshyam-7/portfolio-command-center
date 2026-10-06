// State Management
let currentUser = null;
let currentAuthMode = 'login';
let selectedPeerId = null;
let chatPollTimer = null;
let videoStream = null;

// Unique device identification per browser instance
function getDeviceId() {
  let id = localStorage.getItem('device_id');
  if (!id) {
    id = 'dev_' + Math.random().toString(36).substring(2, 10) + '_' + Date.now();
    localStorage.setItem('device_id', id);
  }
  return id;
}

// Authenticated fetch wrapper that attaches Bearer token automatically
async function apiFetch(url, options = {}) {
  const token = localStorage.getItem('auth_token');
  const headers = Object.assign({}, options.headers || {});
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return fetch(url, { ...options, headers });
}

// Session Initializer on page load
document.addEventListener('DOMContentLoaded', async () => {
  await verifySession();
});

async function verifySession() {
  const token = localStorage.getItem('auth_token');
  if (!token) {
    onLogoutComplete();
    return;
  }

  try {
    const res = await apiFetch('/api/auth/me');
    if (res.ok) {
      const data = await res.json();
      onLoginSuccess(data);
    } else {
      localStorage.removeItem('auth_token');
      onLogoutComplete();
    }
  } catch (err) {
    onLogoutComplete();
  }
}

// Auth Modal Controls
function openAuthModal() {
  document.getElementById('auth-modal').style.display = 'flex';
  document.getElementById('auth-error').style.display = 'none';
  switchAuthTab('login');
}

function closeAuthModal() {
  document.getElementById('auth-modal').style.display = 'none';
}

function switchAuthTab(mode) {
  currentAuthMode = mode;
  const tabLogin = document.getElementById('tab-btn-login');
  const tabReg = document.getElementById('tab-btn-register');
  const pairingSec = document.getElementById('pairing-section');
  const instruction = document.getElementById('auth-tab-instruction');
  const submitBtn = document.getElementById('auth-submit-btn');
  const errorBox = document.getElementById('auth-error');
  errorBox.style.display = 'none';

  if (mode === 'register') {
    tabReg.classList.add('active');
    tabLogin.classList.remove('active');
    pairingSec.style.display = 'none'; // Dynamic members do not need Creator master key
    instruction.innerText = 'Create an independent Member account to access quest logs, ranks, and 1-on-1 comms.';
    submitBtn.innerText = 'CREATE ACCOUNT';
  } else {
    tabLogin.classList.add('active');
    tabReg.classList.remove('active');
    pairingSec.style.display = 'block';
    instruction.innerText = 'Enter credentials. Creator profile is hardware-locked to 3 authorized devices.';
    submitBtn.innerText = 'AUTHENTICATE';
  }
}

// Auth Form Submission
async function submitAuth() {
  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value;
  const deviceLabel = document.getElementById('auth-device-label').value;
  const masterKey = document.getElementById('auth-master-key').value;
  const errorBox = document.getElementById('auth-error');

  errorBox.style.display = 'none';

  if (!username || !password) {
    showAuthError('Username and password cannot be blank.');
    return;
  }

  const deviceId = getDeviceId();

  if (currentAuthMode === 'register') {
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username,
          password: password,
          device_id: deviceId,
          device_label: deviceLabel
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showAuthError(data.detail || 'Failed to create user account.');
        return;
      }
      alert('Registration successful! Please login with your new credentials.');
      switchAuthTab('login');
      document.getElementById('auth-username').value = username;
      document.getElementById('auth-password').value = '';
    } catch (e) {
      showAuthError('Network error connecting to registration service.');
    }
  } else {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username,
          password: password,
          device_id: deviceId,
          device_label: deviceLabel,
          master_key: masterKey
        })
      });
      const data = await res.json();
      if (!res.ok) {
        showAuthError(data.detail || 'Invalid username, password, or device key.');
        return;
      }
      
      // Store token for all authenticated requests
      if (data.token) {
        localStorage.setItem('auth_token', data.token);
      }
      
      closeAuthModal();
      await verifySession();
    } catch (e) {
      showAuthError('Network error connecting to authentication service.');
    }
  }
}

function showAuthError(msg) {
  const errorBox = document.getElementById('auth-error');
  errorBox.innerText = msg;
  errorBox.style.display = 'block';
}

async function logout() {
  try {
    await apiFetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {
    // Session cleanup proceeds regardless
  }
  localStorage.removeItem('auth_token');
  currentUser = null;
  onLogoutComplete();
}

function onLoginSuccess(user) {
  currentUser = user;
  document.getElementById('banner-auth-text').innerText = `AUTHENTICATED: ${user.username.toUpperCase()} (${user.role.toUpperCase()})`;
  document.getElementById('banner-auth-btn').style.display = 'none';
  document.getElementById('banner-logout-btn').style.display = 'inline-block';
  document.getElementById('banner-biometric-btn').style.display = 'inline-block';

  document.getElementById('user-display-name').innerText = `${user.username.toUpperCase()} [${user.role.toUpperCase()}]`;
  document.getElementById('user-display-lvl').innerText = user.role === 'creator' ? 'LVL 03 (SEM 3)' : 'LVL 01 (MEMBER)';

  // CADENCE RESTRICTION: Show command centre root box strictly for Ganshyam (creator)
  const creatorBox = document.getElementById('creator-cadence-box');
  if (user.role === 'creator' && user.username === 'ganshyam') {
    creatorBox.style.display = 'block';
  } else {
    creatorBox.style.display = 'none';
  }

  loadQuests();
  loadTeamProgress();
  initCommsChannel();
}

function onLogoutComplete() {
  currentUser = null;
  document.getElementById('banner-auth-text').innerText = 'AUTHENTICATION REQUIRED: ENTER TERMINAL LOGIN';
  document.getElementById('banner-auth-btn').style.display = 'inline-block';
  document.getElementById('banner-logout-btn').style.display = 'none';
  document.getElementById('banner-biometric-btn').style.display = 'none';
  document.getElementById('creator-cadence-box').style.display = 'none';

  document.getElementById('user-display-name').innerText = 'GUEST_RECON [UNVERIFIED]';
  document.getElementById('user-display-lvl').innerText = 'LVL 00 (RECON)';

  document.getElementById('quest-list-container').innerHTML = `
    <div class="quest-item">
      <span>Authenticate profile to decrypt syllabus quest logs...</span>
      <span class="badge">LOCKED</span>
    </div>
  `;
  document.getElementById('quest-count').innerText = '0 QUESTS';

  if (chatPollTimer) clearInterval(chatPollTimer);
  document.getElementById('chat-contacts-list').innerHTML = `
    <div style="padding: 10px; font-size: 10px; color: #64748b;">No active links. Authenticate to sync contacts.</div>
  `;
  document.getElementById('chat-messages-box').innerHTML = `
    <div style="color: #64748b; margin: auto;">Select a peer from the left panel to load decrypted transmission log.</div>
  `;
}

// Quests and Team Matrix
// Load Quests with dynamic submission buttons
async function loadQuests() {
  try {
    const res = await apiFetch('/api/quests');
    if (!res.ok) return;
    const quests = await res.json();
    const list = document.getElementById('quest-list-container');
    list.innerHTML = '';
    document.getElementById('quest-count').innerText = `${quests.length} QUESTS`;

    quests.forEach(q => {
      const item = document.createElement('div');
      item.className = 'quest-item';
      
      const isDone = q.status === 'COMPLETED' || q.status === 'SUBMITTED';
      const statusClass = isDone ? 'badge-done' : '';
      const displayStatus = q.status || 'PENDING';

      item.innerHTML = `
        <div style="max-width: 65%;">
          <strong style="color: var(--text-gold);">${q.code || 'QUEST'}:</strong> ${q.title}
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="badge ${statusClass}">${displayStatus}</span>
          <button class="pixel-btn" style="padding: 3px 8px; font-size: 10px;" onclick="openQuestModal(${q.id}, '${escapeHtml(q.title)}')">
            ${isDone ? 'RESUBMIT' : 'SUBMIT'}
          </button>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    console.error('Failed to load quests', err);
  }
}

// Escape helper to prevent quote breaking in HTML attributes
function escapeHtml(text) {
  return text.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// Quest Submission Modal Handlers
function openQuestModal(questId, title) {
  document.getElementById('quest-modal').style.display = 'flex';
  document.getElementById('quest-submit-error').style.display = 'none';
  document.getElementById('quest-modal-title').innerText = `SUBMIT: ${title}`;
  document.getElementById('submit-quest-id').value = questId;
  document.getElementById('submit-quest-url').value = '';
  document.getElementById('submit-quest-notes').value = '';
}

function closeQuestModal() {
  document.getElementById('quest-modal').style.display = 'none';
}

async function submitQuestProof() {
  const questId = document.getElementById('submit-quest-id').value;
  const url = document.getElementById('submit-quest-url').value.trim();
  const notes = document.getElementById('submit-quest-notes').value.trim();
  const errorBox = document.getElementById('quest-submit-error');

  errorBox.style.display = 'none';

  if (!url && !notes) {
    errorBox.innerText = 'Please provide a repository/demo link or execution notes.';
    errorBox.style.display = 'block';
    return;
  }

  try {
    const res = await apiFetch('/api/quests/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quest_id: parseInt(questId),
        submission_url: url,
        notes: notes
      })
    });

    const data = await res.json();
    if (!res.ok) {
      errorBox.innerText = data.detail || 'Submission failed.';
      errorBox.style.display = 'block';
      return;
    }

    alert(data.message || 'Submission received!');
    closeQuestModal();
    await loadQuests();
    await loadTeamProgress();
  } catch (e) {
    errorBox.innerText = 'Network error transmitting submission.';
    errorBox.style.display = 'block';
  }
}

async function loadTeamProgress() {
  try {
    const res = await apiFetch('/api/team/progress');
    if (!res.ok) return;
    const team = await res.json();
    const container = document.getElementById('team-progress-container');
    container.innerHTML = '';

    team.forEach(t => {
      const row = document.createElement('div');
      row.className = 'quest-item';
      row.innerHTML = `
        <span><strong>${t.username}</strong> [${t.role.toUpperCase()}]</span>
        <span class="badge badge-done">XP: ${t.xp || 100}</span>
      `;
      container.appendChild(row);
    });
  } catch (err) {
    console.error('Failed to load progress', err);
  }
}

// 1-on-1 Encrypted Comms Channel
async function initCommsChannel() {
  if (chatPollTimer) clearInterval(chatPollTimer);
  await loadChatContacts();
  chatPollTimer = setInterval(pollChatMessages, 3000);
}

async function loadChatContacts() {
  try {
    const res = await apiFetch('/api/chat/contacts');
    if (!res.ok) return;
    const contacts = await res.json();
    const list = document.getElementById('chat-contacts-list');
    list.innerHTML = '';

    if (contacts.length === 0) {
      list.innerHTML = `<div style="padding: 8px; font-size: 10px; color: #64748b;">No peers online.</div>`;
      return;
    }

    contacts.forEach(peer => {
      const el = document.createElement('div');
      el.className = `contact-item ${selectedPeerId === peer.id ? 'active' : ''}`;
      el.innerHTML = `
        <span>${peer.username}</span>
        <span class="badge ${peer.role === 'creator' ? 'badge-creator' : ''}">${peer.role}</span>
      `;
      el.onclick = () => selectPeer(peer.id, peer.username);
      list.appendChild(el);
    });
  } catch (e) {
    console.error('Failed loading contacts', e);
  }
}

function selectPeer(peerId, peerName) {
  selectedPeerId = peerId;
  document.getElementById('chat-active-peer-label').innerText = `CHANNEL: PEER [${peerName.toUpperCase()}]`;
  loadChatContacts();
  pollChatMessages();
}

async function pollChatMessages() {
  if (!selectedPeerId) return;
  try {
    const res = await apiFetch(`/api/chat/history/${selectedPeerId}`);
    if (!res.ok) return;
    const messages = await res.json();
    const box = document.getElementById('chat-messages-box');
    box.innerHTML = '';

    if (messages.length === 0) {
      box.innerHTML = `<div style="color: #64748b; margin: auto;">No transmissions exchanged yet.</div>`;
      return;
    }

    messages.forEach(m => {
      const bubble = document.createElement('div');
      const isSelf = m.sender_id === currentUser.id;
      bubble.className = `msg-bubble ${isSelf ? 'msg-self' : 'msg-peer'}`;
      bubble.innerHTML = `
        <div style="font-size: 9px; opacity: 0.7; margin-bottom: 2px;">${isSelf ? 'YOU' : 'PEER'} • ${m.created_at || ''}</div>
        <div>${m.content}</div>
      `;
      box.appendChild(bubble);
    });
    box.scrollTop = box.scrollHeight;
  } catch (e) {
    console.error('Chat poll failed', e);
  }
}

async function sendChatMessage() {
  const input = document.getElementById('chat-msg-input');
  const text = input.value.trim();
  if (!text || !selectedPeerId) return;

  try {
    const res = await apiFetch('/api/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        receiver_id: selectedPeerId,
        content: text
      })
    });
    if (res.ok) {
      input.value = '';
      await pollChatMessages();
    }
  } catch (e) {
    alert('Transmission failed.');
  }
}

// Creator Root Cadence Executor
async function executeCreatorCommand(action) {
  const log = document.getElementById('creator-exec-log');
  log.innerText = `[${new Date().toLocaleTimeString()}] Executing cadence root directive: ${action}...`;
  try {
    const res = await apiFetch('/api/command/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action })
    });
    const data = await res.json();
    if (!res.ok) {
      log.innerText = `[ERROR] ${data.detail || 'Execution denied'}`;
    } else {
      log.innerText = `[OK] Directive confirmed: ${data.message || 'Operation successful'}`;
    }
  } catch (e) {
    log.innerText = '[ERROR] Cadence bridge connection failure.';
  }
}

// Biometric Calibration Webcam Handlers
async function openBiometricModal() {
  document.getElementById('biometric-modal').style.display = 'flex';
  document.getElementById('biometric-error').style.display = 'none';
  const video = document.getElementById('biometric-video');

  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    video.srcObject = videoStream;
  } catch (err) {
    document.getElementById('biometric-error').innerText = 'Webcam access denied or unavailable.';
    document.getElementById('biometric-error').style.display = 'block';
  }
}

function closeBiometricModal() {
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }
  document.getElementById('biometric-modal').style.display = 'none';
}

async function captureReferenceBiometric() {
  const video = document.getElementById('biometric-video');
  const canvas = document.getElementById('biometric-canvas');
  const errorBox = document.getElementById('biometric-error');
  errorBox.style.display = 'none';

  if (!video.videoWidth) {
    errorBox.innerText = 'Camera feed not ready.';
    errorBox.style.display = 'block';
    return;
  }

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const base64Data = canvas.toDataURL('image/jpeg');

  try {
    const res = await apiFetch('/api/auth/biometric-register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_base64: base64Data })
    });
    const data = await res.json();
    if (!res.ok) {
      errorBox.innerText = `Biometric calibration failed: ${data.detail || 'No face detected'}`;
      errorBox.style.display = 'block';
    } else {
      alert('Biometric template calibrated and registered successfully!');
      closeBiometricModal();
    }
  } catch (err) {
    errorBox.innerText = 'Network error during biometric transmission.';
    errorBox.style.display = 'block';
  }
}