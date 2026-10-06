import sqlite3
import hashlib
import base64
import re
import cv2
import requests
import numpy as np
from typing import ClassVar
from pydantic import BaseModel
from datetime import date
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pydantic import BaseModel
from typing import Optional

def verify_creator_clearance(current_user: dict):
    """Enforces that only the creator ('ganshyam') has administrative command clearance."""
    if current_user.get("role") != "creator" or current_user.get("username") != "ganshyam":
        raise HTTPException(
            status_code=403, 
            detail="CLEARANCE DENIED: Command center root controls restricted to Creator profile."
        )
class RegisterRequest(BaseModel):
    username: str
    password: str
    device_id: str
    device_label: Optional[str] = "Web Client"

class SendMessageRequest(BaseModel):
    receiver_id: int
    content: str

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "command_center.db"
FRONTEND_PATH = Path(__file__).resolve().parent.parent / "frontend"
CREATOR_MASTER_PAIRING_KEY="Ganshyam@77"
app = FastAPI(title="Multi-User RPG Command Center with Deep Repo Verification")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH,timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# --- Request Models ---

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str
    device_label: Optional[str]="Personal Device"
    master_key: Optional[str]=None
    CREATOR_MASTER_PAIRING_KEY :ClassVar[str]="Ganshyam@77"

class FaceRegisterRequest(BaseModel):
    image_base64: str

class QuestSubmissionRequest(BaseModel):
    repo_url: str
    device_id: str
    image_base64: str

class PodAssignmentRequest(BaseModel):
    quest_id: int
    user_id: int
    pod_name: str
    role_title: str

class QuestSubmitRequest(BaseModel):
    quest_id: int
    submission_url: Optional[str] = ""
    notes: Optional[str] = ""

# --- Auth Dependency ---

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization token.")
    try:
        username = authorization.replace("Bearer ", "").strip()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?;", (username,))
        user = c.fetchone()
        conn.close()
        if not user:
            raise HTTPException(status_code=401, detail="User not recognized.")
        return dict(user)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session token.")

@app.post("/api/auth/register")
@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    username_clean = payload.username.strip().lower()
    if not username_clean or len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    if username_clean in ["ganshyam", "creator", "admin"]:
        raise HTTPException(status_code=400, detail="Username reserved.")

    conn = get_db()
    c = conn.cursor()
    try:
        # Check if username already exists
        c.execute("SELECT id FROM users WHERE username = ?;", (username_clean,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Username already exists. Choose another.")

        password_hashed = hash_pw(payload.password)
        full_name = username_clean.capitalize()
        github_handle = username_clean  # Satisfies UNIQUE NOT NULL

        c.execute("""
            INSERT INTO users (
                username, 
                password_hash, 
                full_name, 
                role, 
                github_username, 
                registered_device_id
            ) VALUES (?, ?, ?, 'member', ?, ?);
        """, (username_clean, password_hashed, full_name, github_handle, payload.device_id))
        
        conn.commit()
        return {"status": "success", "message": "Account created successfully. Please login."}
    finally:
        conn.close()

    r
# --- Authentication ---

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?;", 
              (payload.username, hash_pw(payload.password)))
    user = c.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    user_dict = dict(user)

    # === STRICT CREATOR 3-DEVICE WHITELIST (Ubuntu, Windows, Mobile) ===
    if user_dict["role"] == "creator":
        c.execute("SELECT device_id, device_label FROM creator_trusted_devices WHERE device_id = ?;", (payload.device_id,))
        trusted = c.fetchone()

        if not trusted:
            # Check how many devices are currently registered (Max: 3)
            c.execute("SELECT COUNT(*) as total FROM creator_trusted_devices;")
            total_slots = c.fetchone()["total"]

            if total_slots >= 3:
                conn.close()
                raise HTTPException(
                    status_code=403,
                    detail="ACCESS DENIED: Creator device limit reached (3/3 slots full). Unauthorized device."
                )

            # Enrolling a new slot requires the Master Key
            if payload.master_key != CREATOR_MASTER_PAIRING_KEY:
                conn.close()
                raise HTTPException(
                    status_code=403,
                    detail=f"DEVICE NOT ENROLLED ({total_slots}/3 slots used). Enter valid Master Pairing Key to register this device (Ubuntu/Windows/Mobile)."
                )

            # Register new trusted device slot
            c.execute("""
                INSERT INTO creator_trusted_devices (device_id, device_label, registered_at)
                VALUES (?, ?, ?);
            """, (payload.device_id, payload.device_label, date.today().isoformat()))
            conn.commit()

    # === MEMBER SINGLE-DEVICE BINDING ===
    else:
        if user_dict["registered_device_id"] is None:
            c.execute("UPDATE users SET registered_device_id = ? WHERE id = ?;", (payload.device_id, user_dict["id"]))
            conn.commit()
            user_dict["registered_device_id"] = payload.device_id
        elif user_dict["registered_device_id"] != payload.device_id:
            conn.close()
            raise HTTPException(status_code=403, detail="Device Mismatch! Your account is bound to another device.")

    conn.close()
    return {"token": user_dict["username"], "user": user_dict}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return user

# --- OpenCV Face Registration ---

@app.post("/api/user/register-face")
def register_face(payload: FaceRegisterRequest, user: dict = Depends(get_current_user)):
    try:
        _, encoded = payload.image_base64.split(",", 1) if "," in payload.image_base64 else ("", payload.image_base64)
        img_bytes = base64.b64decode(encoded)
        frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5)

        if len(faces) == 0:
            raise HTTPException(status_code=400, detail="No face detected. Center your face with good lighting.")

        (x, y, w, h) = faces[0]
        face_crop = cv2.resize(gray[y:y+h, x:x+w], (128, 128))

        conn = get_db()
        c = conn.cursor()
        c.execute("REPLACE INTO user_faces (user_id, face_encoding) VALUES (?, ?);", 
                  (user["id"], face_crop.tobytes()))
        c.execute("UPDATE users SET face_registered = 1 WHERE id = ?;", (user["id"],))
        conn.commit()
        conn.close()

        return {"message": "Facial biometric profile successfully calibrated!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Biometric calibration failed: {str(e)}")

# --- Team Roster & Quests ---

@app.get("/api/team/progress")
def get_team_progress():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.full_name, u.role, u.github_username, u.hp, u.current_xp, u.current_semester,
               COUNT(p.id) as quests_cleared
        FROM users u
        LEFT JOIN user_quest_progress p ON u.id = p.user_id AND p.status = 'COMPLETED'
        GROUP BY u.id
        ORDER BY u.current_xp DESC;
    """)
    team = [dict(r) for r in c.fetchall()]
    conn.close()
    return team

@app.get("/api/quests")
def get_quests(user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        # Fetch all Semester 3 milestones excluding Portfolio Command Center
        c.execute("""
            SELECT * FROM roadmap_milestones 
            WHERE title NOT LIKE '%Portfolio Command Center%'
            ORDER BY id ASC;
        """)
        milestones = [dict(r) for r in c.fetchall()]

        # Attach member-specific progress safely
        for m in milestones:
            try:
                c.execute("""
                    SELECT * FROM user_quest_progress 
                    WHERE quest_id = ? AND user_id = ?;
                """, (m["id"], user["id"]))
                prog = c.fetchone()
                if prog:
                    p_dict = dict(prog)
                    m["status"] = p_dict.get("status") or "SUBMITTED"
                    m["repo_url"] = p_dict.get("repo_url") or ""
                else:
                    m["status"] = "PENDING"
            except Exception:
                m["status"] = "PENDING"

        return milestones
    finally:
        conn.close()

@app.post("/api/quests/submit")
def submit_quest(payload: QuestSubmitRequest, user: dict = Depends(get_current_user)):
    if not payload.submission_url.strip() and not payload.notes.strip():
        raise HTTPException(status_code=400, detail="Please provide a submission repository URL or notes.")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM roadmap_milestones WHERE id = ?;", (payload.quest_id,))
        quest = c.fetchone()
        if not quest:
            raise HTTPException(status_code=404, detail="Milestone quest not found.")

        quest_dict = dict(quest)
        xp_award = quest_dict.get("xp_reward", 50) or 50

        c.execute("SELECT id FROM user_quest_progress WHERE user_id = ? AND quest_id = ?;", (user["id"], payload.quest_id))
        existing = c.fetchone()

        if existing:
            c.execute("""
                UPDATE user_quest_progress 
                SET repo_url = ?, status = 'SUBMITTED', submitted_at = CURRENT_TIMESTAMP 
                WHERE id = ?;
            """, (payload.submission_url.strip(), existing["id"]))
        else:
            c.execute("""
                INSERT INTO user_quest_progress (user_id, quest_id, repo_url, status, submitted_at)
                VALUES (?, ?, ?, 'SUBMITTED', CURRENT_TIMESTAMP);
            """, (user["id"], payload.quest_id, payload.submission_url.strip()))

        c.execute("UPDATE users SET current_xp = current_xp + ? WHERE id = ?;", (xp_award, user["id"]))
        conn.commit()
        return {"status": "success", "message": f"Quest '{quest_dict.get('title')}' submitted! +{xp_award} XP awarded."}
    finally:
        conn.close()
# --- Creator Admin ---

@app.post("/api/admin/assign-pod")
def assign_pod(payload: PodAssignmentRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "creator":
        raise HTTPException(status_code=403, detail="Only the Creator can manage Pod assignments.")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO pod_allocations (quest_id, user_id, pod_name, role_title)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(quest_id, user_id) DO UPDATE SET
            pod_name = excluded.pod_name,
            role_title = excluded.role_title;
    """, (payload.quest_id, payload.user_id, payload.pod_name, payload.role_title))
    conn.commit()
    conn.close()
    return {"message": "Pod assignment updated successfully."}

@app.post("/api/command/execute")
def execute_system_command(payload: dict, user: dict = Depends(get_current_user)):
    verify_creator_clearance(user)
    # Root/creator-only commands execute here...

@app.get("/api/chat/contacts")
def get_chat_contacts(user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    # List all users available to chat with, excluding yourself
    c.execute("SELECT id, username, role FROM users WHERE id != ? ORDER BY role DESC, username ASC;", (user["id"],))
    contacts = [dict(r) for r in c.fetchall()]
    conn.close()
    return contacts

@app.get("/api/chat/history/{peer_id}")
def get_chat_history(peer_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, sender_id, receiver_id, content, created_at 
        FROM private_messages 
        WHERE (sender_id = ? AND receiver_id = ?) 
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at ASC 
        LIMIT 100;
    """, (user["id"], peer_id, peer_id, user["id"]))
    
    messages = [dict(r) for r in c.fetchall()]
    
    # Mark messages as read
    c.execute("""
        UPDATE private_messages SET is_read = 1 
        WHERE receiver_id = ? AND sender_id = ?;
    """, (user["id"], peer_id))
    conn.commit()
    conn.close()
    return messages

@app.post("/api/chat/send")
def send_private_message(payload: SendMessageRequest, user: dict = Depends(get_current_user)):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO private_messages (sender_id, receiver_id, content)
        VALUES (?, ?, ?);
    """, (user["id"], payload.receiver_id, payload.content.strip()))
    
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"status": "sent", "message_id": msg_id}
# --- Deep Repository Content Verification Helper ---

def verify_github_repository_contents(owner: str, repo: str, required_exts: list, required_keywords: list):
    """
    Calls the GitHub REST API to inspect the repository tree and scans files
    to verify that the actual project implementation meets the task description.
    """
    headers = {"User-Agent": "Portfolio-Verification-Bot"}
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    
    resp = requests.get(api_url, headers=headers, timeout=8)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"GitHub repository '{owner}/{repo}' not found or is private.")
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"GitHub API Error: HTTP {resp.status_code}")

    files = resp.json()
    if not isinstance(files, list) or len(files) == 0:
        raise HTTPException(status_code=422, detail="Repository is empty! No files found.")

    # 1. Extension Verification
    file_names = [f["name"] for f in files if "name" in f]
    matched_ext = any(any(fname.endswith(ext) for ext in required_exts) for fname in file_names)
    
    # Check inside subdirectories (1 level deep) if root didn't match
    subdirs = [f["url"] for f in files if f.get("type") == "dir"]
    for sdir in subdirs[:3]:
        s_resp = requests.get(sdir, headers=headers, timeout=5)
        if s_resp.status_code == 200 and isinstance(s_resp.json(), list):
            for sf in s_resp.json():
                file_names.append(sf.get("name", ""))
                if any(sf.get("name", "").endswith(ext) for ext in required_exts):
                    matched_ext = True

    if not matched_ext:
        raise HTTPException(
            status_code=422,
            detail=f"Task Mismatch: Repository lacks expected file types ({', '.join(required_exts)}) for this project."
        )

    # 2. Content & Keyword Inspection
    # Fetch content of key code files or README to confirm the code does what the project says
    combined_code_text = ""
    for f in files:
        if f.get("type") == "file" and any(f["name"].endswith(ext) for ext in required_exts + [".md", ".txt"]):
            raw_url = f.get("download_url")
            if raw_url:
                try:
                    f_resp = requests.get(raw_url, headers=headers, timeout=4)
                    if f_resp.status_code == 200:
                        combined_code_text += " " + f_resp.text.lower()
                except Exception:
                    pass

    # Verify that at least 2 required implementation keywords exist in the repository's code
    found_keywords = [kw for kw in required_keywords if kw in combined_code_text]
    if len(found_keywords) < min(2, len(required_keywords)):
        missing = [kw for kw in required_keywords if kw not in found_keywords]
        raise HTTPException(
            status_code=422,
            detail=f"Task Verification Failed: Code does not match the project requirements. Missing implementations: {', '.join(missing)}."
        )

# --- Biometric & Content Submission Route ---

@app.post("/api/quests/{quest_id}/submit")
def submit_quest(quest_id: int, payload: QuestSubmissionRequest, user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()

    # 1. Single-Device Security Verification
    if user["registered_device_id"] and user["registered_device_id"] != payload.device_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Device Mismatch! You cannot upload from an unauthorized device.")

    # 2. Fetch Quest Metadata
    c.execute("SELECT * FROM roadmap_milestones WHERE id = ?;", (quest_id,))
    quest = c.fetchone()
    if not quest:
        conn.close()
        raise HTTPException(status_code=404, detail="Quest not found.")

    expected_slug = quest["required_repo_name"].lower()
    user_git = user["github_username"].lower()
    submitted_url = payload.repo_url.strip()

    # 3. GitHub URL & Account Ownership Verification
    match = re.search(r"github\.com/([^/]+)/([^/]+)", submitted_url)
    if not match:
        conn.close()
        raise HTTPException(status_code=422, detail="Invalid GitHub URL format.")

    owner, repo_name = match.group(1).lower(), match.group(2).lower().replace(".git", "")

    if owner != user_git:
        conn.close()
        raise HTTPException(
            status_code=422,
            detail=f"Identity Fraud Blocked! Repository belongs to '{owner}', but your account is bound to GitHub '@{user_git}'."
        )

    if expected_slug not in repo_name:
        conn.close()
        raise HTTPException(
            status_code=422,
            detail=f"Slug Mismatch! The repository name must correspond to this task: '{expected_slug}'."
        )

    # 4. Deep Repository Code Verification
    req_exts = [e.strip() for e in quest["required_extensions"].split(",")]
    req_kws = [k.strip() for k in quest["required_keywords"].split(",")]
    verify_github_repository_contents(owner, repo_name, req_exts, req_kws)

    # 5. OpenCV Biometric Facial Verification
    c.execute("SELECT face_encoding FROM user_faces WHERE user_id = ?;", (user["id"],))
    face_row = c.fetchone()
    if not face_row:
        conn.close()
        raise HTTPException(status_code=400, detail="No registered biometric profile! Calibrate your face first.")

    registered_crop = np.frombuffer(face_row["face_encoding"], dtype=np.uint8).reshape((128, 128))

    try:
        _, encoded = payload.image_base64.split(",", 1) if "," in payload.image_base64 else ("", payload.image_base64)
        img_bytes = base64.b64decode(encoded)
        frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=4)

        if len(detected_faces) == 0:
            conn.close()
            raise HTTPException(status_code=401, detail="Biometric Scan Failed: No face visible to webcam.")

        (x, y, w, h) = detected_faces[0]
        live_crop = cv2.resize(gray[y:y+h, x:x+w], (128, 128))
        match_score = cv2.matchTemplate(live_crop, registered_crop, cv2.TM_CCOEFF_NORMED)[0][0]

        if match_score < 0.28:
            conn.close()
            raise HTTPException(status_code=401, detail="Biometric Rejected! Live camera face does not match account owner.")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=401, detail=f"Biometric Validation Failure: {str(e)}")

    # 6. Scoring & Completion
    today = date.today()
    deadline_date = date.fromisoformat(quest["deadline"])
    days_diff = (deadline_date - today).days
    base_xp = quest["base_xp"]
    hp_penalty = 0

    if days_diff >= 0:
        early_bonus = min(100, days_diff * 15)
        earned_xp = base_xp + early_bonus
        msg = f"Task Verified & Face Authenticated! +{base_xp} Base XP, +{early_bonus} Early XP granted!"
    else:
        days_late = abs(days_diff)
        earned_xp = max(50, int(base_xp * 0.65))
        hp_penalty = min(40, days_late * 5)
        msg = f"Task Verified! Overdue by {days_late} days. +{earned_xp} XP, -{hp_penalty} HP applied."

    c.execute("""
        INSERT INTO user_quest_progress (user_id, quest_id, status, submitted_repo_url, verified_device_id, completed_at)
        VALUES (?, ?, 'COMPLETED', ?, ?, ?)
        ON CONFLICT(user_id, quest_id) DO UPDATE SET
            status = 'COMPLETED',
            submitted_repo_url = excluded.submitted_repo_url,
            verified_device_id = excluded.verified_device_id,
            completed_at = excluded.completed_at;
    """, (user["id"], quest_id, payload.repo_url, payload.device_id, today.isoformat()))

    new_hp = max(1, user["hp"] - hp_penalty)
    new_xp = user["current_xp"] + earned_xp
    c.execute("UPDATE users SET hp = ?, current_xp = ? WHERE id = ?;", (new_hp, new_xp, user["id"]))

    conn.commit()
    conn.close()

    return {"success": True, "message": msg}

# --- Static UI Serving ---

app.mount("/static", StaticFiles(directory=FRONTEND_PATH), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse(FRONTEND_PATH / "index.html")