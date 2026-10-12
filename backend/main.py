import os
import sqlite3
import hashlib
import secrets
import json
import urllib.request
import re
from datetime import date
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==============================================================================
# Database Configuration & Self-Healing Auto-Migrations
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "command_center.db")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${key.hex()}"

def verify_password(stored_hash: str, provided_password: str) -> bool:
    if not stored_hash or '$' not in stored_hash:
        return False
    salt, key_hex = stored_hash.split('$', 1)
    test_key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return secrets.compare_digest(test_key.hex(), key_hex)

def init_database():
    conn = get_db()
    c = conn.cursor()

    # 1. Base Users Table (Now using github_handle instead of biometrics)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            github_handle TEXT,
            role TEXT DEFAULT 'member',
            current_xp INTEGER DEFAULT 0,
            current_semester INTEGER DEFAULT 3,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    c.execute("PRAGMA table_info(users);")
    user_cols = [r[1] for r in c.fetchall()]
    
    # Auto-migrate missing columns
    user_patches = [
        ("github_handle", "TEXT"),
        ("current_xp", "INTEGER DEFAULT 0"),
        ("current_semester", "INTEGER DEFAULT 3"),
        ("role", "TEXT DEFAULT 'member'")
    ]
    for col, definition in user_patches:
        if col not in user_cols:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition};")
            except Exception:
                pass

    # Drop legacy constraints if they exist
    for legacy_col in ["full_name", "email", "biometric_encoding"]:
        if legacy_col in user_cols:
            try:
                c.execute(f"ALTER TABLE users DROP COLUMN {legacy_col};")
            except Exception:
                pass

    # Seed Master Creator Account
    c.execute("SELECT id FROM users WHERE LOWER(username) = 'ganshyam';")
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (username, password_hash, role, current_xp, current_semester, github_handle)
            VALUES ('ganshyam', ?, 'creator', 0, 3, 'ganshyam-7');
        """, (hash_password("ganshyam123"),))

    # 2. Quest Progress Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_quest_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            repo_url TEXT,
            notes TEXT DEFAULT 'AUTOMATICALLY_VERIFIED',
            status TEXT DEFAULT 'PENDING',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, quest_id)
        );
    """)

    c.execute("PRAGMA table_info(user_quest_progress);")
    q_cols = [r[1] for r in c.fetchall()]
    for col in ["repo_url", "notes", "status", "submitted_at"]:
        if col not in q_cols:
            try:
                c.execute(f"ALTER TABLE user_quest_progress ADD COLUMN {col} TEXT;")
            except Exception:
                pass

    # 3. Private Messaging
    c.execute("""
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Roadmap Milestones Catalog
    c.execute("""
        CREATE TABLE IF NOT EXISTS roadmap_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            title TEXT NOT NULL,
            description TEXT,
            semester INTEGER DEFAULT 3,
            tier TEXT DEFAULT 'minor',
            start_date TEXT,
            end_date TEXT,
            xp_reward INTEGER DEFAULT 100,
            tech_stack TEXT
        );
    """)

    c.execute("SELECT COUNT(*) FROM roadmap_milestones;")
    if c.fetchone()[0] == 0:
        curriculum = [
            ("SEM3-M1", "B2B Procurement Scraper", 3, "minor", "2026-10-19", "2026-10-25", 100, 
             "Architect and deploy an automated B2B procurement scraping engine leveraging Python, Playwright, and BeautifulSoup. The system navigates dynamic wholesale marketplaces to extract structured product tiers and wholesale lot pricing, archiving into SQLite.", "Python, Playwright, BeautifulSoup, SQLite"),
            ("SEM3-MAJ1", "Smart Retail POS Terminal", 3, "major", "2026-10-11", "2026-11-08", 200,
             "Design and deliver a production-ready Smart Retail Point-of-Sale (POS) terminal integrating a high-performance FastAPI asynchronous backend with a responsive retro-styled tactical web dashboard. The terminal manages real-time SKU barcode lookups and cart state.", "FastAPI, JavaScript, SQLite"),
            ("SEM4-M4", "Verilog ALU Design", 4, "minor", "2027-02-15", "2027-02-21", 100,
             "Implement an Arithmetic Logic Unit (ALU) modeled in synthesizable IEEE 1364 Verilog RTL. The module performs multi-bit integer arithmetic, boolean logic, and condition code flag generation, supported by a self-checking testbench.", "Verilog RTL, Icarus Verilog"),
            ("SEM4-MAJ1", "FPGA Hardware Smart Scale", 4, "major", "2027-01-10", "2027-02-14", 200,
             "Implement an FPGA-accelerated digital smart weighing scale designed in synthesizable Verilog RTL on Xilinx Artix-7 silicon. The hardware core interfaces with dual 24-bit delta-sigma ADCs via SPI and computes weight taring logic.", "Verilog RTL, FPGA, SPI, DSP Slices")
        ]
        c.executemany("""
            INSERT INTO roadmap_milestones (code, title, semester, tier, start_date, end_date, xp_reward, description, tech_stack)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, curriculum)

    conn.commit()
    conn.close()

init_database()

# ==============================================================================
# FastAPI Application
# ==============================================================================
app = FastAPI(title="ECE Portfolio Command Center", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# Models
# ==============================================================================
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    github_handle: str
    current_semester: Optional[int] = 3

class QuestSubmitRequest(BaseModel):
    quest_id: int
    submission_url: str

class MessageSendRequest(BaseModel):
    receiver_id: int
    content: str

# ==============================================================================
# Auth Dependencies
# ==============================================================================
def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication credentials required.")
    username = authorization.split("Bearer ", 1)[1].strip()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Session expired or invalid user.")
        return dict(row)
    finally:
        conn.close()

def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    username = authorization.split("Bearer ", 1)[1].strip()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?);", (username,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

# ==============================================================================
# Auth Routes
# ==============================================================================
@app.post("/api/auth/login")
def auth_login(payload: LoginRequest):
    username = payload.username.strip().lower()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM users WHERE LOWER(username) = ?;", (username,))
        user = c.fetchone()
        if not user or not verify_password(user["password_hash"], payload.password):
            raise HTTPException(status_code=401, detail="Invalid callsign or passphrase.")

        user_dict = dict(user)
        user_dict.pop("password_hash", None)
        return {"status": "success", "user": user_dict}
    finally:
        conn.close()

@app.post("/api/auth/register")
def auth_register(payload: RegisterRequest):
    username = payload.username.strip().lower()
    password = payload.password.strip()
    github = payload.github_handle.strip()

    if not username or not github:
        raise HTTPException(status_code=400, detail="Callsign and GitHub Handle are required.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Passphrase must be at least 4 characters.")
    if username == "ganshyam":
        raise HTTPException(status_code=403, detail="The master creator callsign is restricted. Please login.")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE LOWER(username) = ?;", (username,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Callsign already taken.")

        pw_hash = hash_password(password)
        # Grants 50 XP starting welcome bonus
        c.execute("""
            INSERT INTO users (username, password_hash, github_handle, role, current_xp, current_semester)
            VALUES (?, ?, ?, 'member', 50, ?);
        """, (username, pw_hash, github, payload.current_semester or 3))
        conn.commit()

        c.execute("SELECT id, username, role, current_xp, current_semester FROM users WHERE LOWER(username) = ?;", (username,))
        return {"status": "success", "user": dict(c.fetchone())}
    finally:
        conn.close()

# ==============================================================================
# Quests & Git-Signature Anti-Proxy Submission
# ==============================================================================
@app.get("/api/quests")
def get_quests(semester: Optional[int] = None, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        target_sem = semester if semester is not None else 3
        user_id = user["id"] if user else 0
        semester_locked = False

        if target_sem > 3:
            if user_id > 0:
                c.execute("""
                    SELECT COUNT(*) FROM roadmap_milestones m
                    LEFT JOIN user_quest_progress p ON m.id = p.quest_id AND p.user_id = ?
                    WHERE m.semester = ? AND (p.status IS NULL OR (p.status != 'SUBMITTED' AND p.status != 'COMPLETED'));
                """, (user_id, target_sem - 1))
                if c.fetchone()[0] > 0:
                    semester_locked = True
            else:
                semester_locked = True

        c.execute("""
            SELECT 
                m.id, m.code, m.title, m.description, m.semester, m.tier,
                m.start_date, m.end_date, m.xp_reward, m.tech_stack,
                COALESCE(p.status, 'PENDING') AS status
            FROM roadmap_milestones m
            LEFT JOIN user_quest_progress p ON m.id = p.quest_id AND p.user_id = ?
            WHERE m.semester = ?
            ORDER BY m.start_date ASC, m.id ASC;
        """, (user_id, target_sem))

        raw_quests = [dict(r) for r in c.fetchall()]
        today = date.today()

        quests = []
        active_quest = None
        previous_completed = True

        for q in raw_quests:
            is_done = q["status"] in ("SUBMITTED", "COMPLETED")
            if q.get("end_date"):
                try:
                    end_d = date.fromisoformat(q["end_date"])
                    q["days_remaining"] = (end_d - today).days
                except Exception:
                    q["days_remaining"] = 999
            else:
                q["days_remaining"] = 999

            if semester_locked:
                q["status"] = "LOCKED"
            else:
                if not previous_completed:
                    q["status"] = "LOCKED"
                elif not is_done:
                    q["status"] = "PENDING"
                    previous_completed = False
                    if active_quest is None:
                        active_quest = q
            quests.append(q)

        return {
            "selected_semester": target_sem,
            "semester_locked": semester_locked,
            "active_quest": active_quest,
            "quests": quests
        }
    finally:
        conn.close()

@app.post("/api/quests/submit")
def submit_quest(payload: QuestSubmitRequest, user: dict = Depends(get_current_user)):
    url = payload.submission_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # 1. Anti-Proxy Verification: Check GitHub Identity & Cryptographic Signature
    match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if not match:
        raise HTTPException(status_code=400, detail="Must be a valid GitHub repository URL.")
    
    owner, repo = match.groups()
    repo = repo.removesuffix(".git")

    if not user.get("github_handle") or owner.lower() != user["github_handle"].lower():
        raise HTTPException(
            status_code=403, 
            detail=f"Anti-Proxy Lock: Repository owner '{owner}' does not match your registered GitHub handle '{user.get('github_handle')}'. You can only submit your own work."
        )

    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    req = urllib.request.Request(api_url, headers={'User-Agent': 'ECE-Command-Center'})
    
    try:
        with urllib.request.urlopen(req) as response:
            commits = json.loads(response.read().decode())
            if not commits:
                raise HTTPException(status_code=400, detail="Repository is empty. Commit your work first.")
            
            latest_commit = commits[0]
            verification = latest_commit.get("commit", {}).get("verification", {})
            
            if not verification.get("verified"):
                reason = verification.get("reason", "Unknown")
                raise HTTPException(
                    status_code=403, 
                    detail=f"⛔ REJECTED: Your latest commit is not cryptographically signed. GitHub says: {reason}. Check your local SSH/GPG keys."
                )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail="Failed to verify repository with GitHub API. Ensure the repository is public.")

    # 2. Grant XP and Record Progress
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, title, xp_reward FROM roadmap_milestones WHERE id = ?;", (payload.quest_id,))
        quest = c.fetchone()
        if not quest:
            raise HTTPException(status_code=404, detail="Milestone directive not found.")

        c.execute("SELECT status FROM user_quest_progress WHERE user_id = ? AND quest_id = ?;", (user["id"], payload.quest_id))
        existing = c.fetchone()
        already_completed = existing and existing["status"] in ("SUBMITTED", "COMPLETED")

        xp_to_award = quest["xp_reward"] if quest["xp_reward"] else 100

        c.execute("""
            INSERT INTO user_quest_progress (user_id, quest_id, repo_url, notes, status, submitted_at)
            VALUES (?, ?, ?, 'AUTOMATICALLY_VERIFIED', 'SUBMITTED', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, quest_id) DO UPDATE SET
                repo_url = excluded.repo_url,
                notes = 'AUTOMATICALLY_VERIFIED',
                status = 'SUBMITTED',
                submitted_at = CURRENT_TIMESTAMP;
        """, (user["id"], payload.quest_id, url))

        if not already_completed:
            c.execute("UPDATE users SET current_xp = current_xp + ? WHERE id = ?;", (xp_to_award, user["id"]))

        conn.commit()

        msg = f"Cryptographic signature verified! Directive '{quest['title']}' submitted."
        if not already_completed:
            msg += f" (+{xp_to_award} XP allocated)"
        return {"status": "success", "message": msg}
    finally:
        conn.close()

# ==============================================================================
# Guild Matrix & Auxiliary Routes
# ==============================================================================
@app.get("/api/team/progress")
def team_progress():
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, username, role, current_xp AS xp FROM users ORDER BY current_xp DESC, id ASC;")
        team = [dict(r) for r in c.fetchall()]
        if team:
            team[0]["is_guild_head"] = True
        return team
    finally:
        conn.close()

@app.get("/api/users")
def get_users(user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, username, role, current_xp FROM users ORDER BY id ASC;")
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()

@app.delete("/api/users/{target_username}")
def remove_cadet(target_username: str, user: dict = Depends(get_current_user)):
    """Permanently deletes a user and wipes their progress (Creator-only)."""
    if user["role"] != "creator":
        raise HTTPException(status_code=403, detail="Access Denied: Only Creator can remove personnel.")

    target = target_username.strip().lower()
    if target == "ganshyam":
        raise HTTPException(status_code=403, detail="Operation rejected: Cannot delete the Master Creator.")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE LOWER(username) = ?;", (target,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cadet not found in database.")

        target_id = row["id"]
        c.execute("DELETE FROM user_quest_progress WHERE user_id = ?;", (target_id,))
        c.execute("DELETE FROM private_messages WHERE sender_id = ? OR receiver_id = ?;", (target_id, target_id))
        c.execute("DELETE FROM users WHERE id = ?;", (target_id,))
        conn.commit()

        return {"status": "success", "message": f"Cadet [{target.upper()}] has been permanently wiped from the system."}
    finally:
        conn.close()

@app.get("/api/alerts")
def get_alerts(user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    alerts = []
    try:
        today = date.today().isoformat()
        active_sem = user.get("current_semester", 3)
        if user["role"] == "creator":
            c.execute("""
                SELECT u.username, m.title, m.end_date 
                FROM roadmap_milestones m
                CROSS JOIN users u
                LEFT JOIN user_quest_progress p ON p.quest_id = m.id AND p.user_id = u.id
                WHERE m.semester = ? AND m.end_date < ? 
                  AND (p.status IS NULL OR (p.status != 'SUBMITTED' AND p.status != 'COMPLETED'))
                  AND u.role = 'member';
            """, (active_sem, today))
            for r in c.fetchall():
                alerts.append(f"MEMBER [{r['username'].upper()}] overdue: {r['title']} ({r['end_date']})")
        else:
            c.execute("""
                SELECT m.title, m.end_date 
                FROM roadmap_milestones m
                LEFT JOIN user_quest_progress p ON p.quest_id = m.id AND p.user_id = ?
                WHERE m.semester = ? AND m.end_date < ? 
                  AND (p.status IS NULL OR (p.status != 'SUBMITTED' AND p.status != 'COMPLETED'));
            """, (user["id"], active_sem, today))
            for r in c.fetchall():
                alerts.append(f"OVERDUE: You missed the deadline for {r['title']} ({r['end_date']})")
        return {"alerts": alerts}
    finally:
        conn.close()

@app.get("/api/messages")
def get_messages(peer_id: int, user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT m.id, m.sender_id, u.username AS sender_name, m.receiver_id, m.content, m.timestamp
            FROM private_messages m
            JOIN users u ON m.sender_id = u.id
            WHERE (m.sender_id = ? AND m.receiver_id = ?)
               OR (m.sender_id = ? AND m.receiver_id = ?)
            ORDER BY m.id ASC;
        """, (user["id"], peer_id, peer_id, user["id"]))
        return [dict(r) for r in c.fetchall()]
    finally:
        conn.close()

@app.post("/api/messages")
def send_message(payload: MessageSendRequest, user: dict = Depends(get_current_user)):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Cannot transmit empty message.")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO private_messages (sender_id, receiver_id, content) VALUES (?, ?, ?);",
                  (user["id"], payload.receiver_id, payload.content.strip()))
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

# ==============================================
# Static File Mounts
# ==============================================
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend_dir")
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend_root")

@app.get("/")
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ECE Portfolio Command Center API active."}
