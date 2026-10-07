import os
import sqlite3
import hashlib
import secrets
from datetime import date, datetime
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==============================================================================
# Database & Path Setup
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

# ==============================================================================
# Cryptographic Password Helpers
# ==============================================================================
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

# ==============================================================================
# Database Schema & Milestone Auto-Seed
# ==============================================================================
def init_database():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT DEFAULT 'member',
            current_xp INTEGER DEFAULT 100,
            current_semester INTEGER DEFAULT 3,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed master creator if not existing
    c.execute("SELECT id FROM users WHERE LOWER(username) = 'ganshyam';")
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (username, password_hash, role, current_xp, current_semester)
            VALUES ('ganshyam', ?, 'creator', 500, 3);
        """, (hash_password("ganshyam123"),))

    # Milestones table
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
            tech_stack TEXT,
            cadence_type TEXT DEFAULT 'sprint',
            required_repo_name TEXT DEFAULT 'pending-repo',
            polish_tag TEXT DEFAULT 'standard',
            domain TEXT DEFAULT 'ECE'
        );
    """)

    # Submissions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_quest_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            repo_url TEXT,
            notes TEXT,
            status TEXT DEFAULT 'PENDING',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, quest_id)
        );
    """)

    # Private messages table
    c.execute("""
        CREATE TABLE IF NOT EXISTS private_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Auto-seed curriculum if milestones are empty
    c.execute("SELECT COUNT(*) FROM roadmap_milestones;")
    if c.fetchone()[0] == 0:
        curriculum = [
            # SEMESTER 3
            ("SEM3-M1", "B2B Procurement Scraper", 3, "minor", "2026-10-19", "2026-10-25", 100, "Automated data pipeline scraping wholesale product catalogs.", "Python, Playwright, BeautifulSoup"),
            ("SEM3-M2", "OpenCV Face/Body Recog Base", 3, "minor", "2026-10-26", "2026-11-01", 100, "Computer vision baseline for real-time facial and pose estimation.", "Python, OpenCV"),
            ("SEM3-M3", "Retail Footfall Counter", 3, "minor", "2026-11-02", "2026-11-08", 100, "Vision-based boundary crossing counter for customer traffic.", "OpenCV, NumPy"),
            ("SEM3-M4", "Digital Signal Filter Sim", 3, "minor", "2026-11-09", "2026-11-15", 100, "FIR/IIR filter design and frequency analysis in Python/NumPy.", "Python, SciPy"),
            ("SEM3-M5", "Local Inventory Sync Script", 3, "minor", "2026-11-16", "2026-11-22", 100, "Offline-to-online relational synchronization daemon.", "Python, SQLite"),
            ("SEM3-MAJ1", "Smart Retail POS Terminal", 3, "major", "2026-10-11", "2026-11-08", 200, "Full transaction processing workflow with local persistence.", "FastAPI, JavaScript"),
            ("SEM3-MAJ2", "STM32 Ethernet Bootloader", 3, "major", "2026-10-26", "2026-11-22", 200, "Remote flashing firmware utility parsing raw Ethernet packets.", "C, ARM Cortex-M"),

            # SEMESTER 4
            ("SEM4-M1", "I2C Store Climate Sensor", 4, "minor", "2027-01-03", "2027-01-17", 100, "Kernel register telemetry polling temperature and humidity over I2C.", "C, Linux Drivers"),
            ("SEM4-M2", "Stepper Motor Conveyor Ctrl", 4, "minor", "2027-01-18", "2027-01-31", 100, "Precision step-timing driver for automated item sorting.", "C++, FreeRTOS"),
            ("SEM4-M3", "Edge AI Surveillance Node", 4, "minor", "2027-02-01", "2027-02-14", 100, "Low-power embedded vision node running inference on edge silicon.", "Python, EdgeTPU"),
            ("SEM4-M4", "Verilog ALU Design", 4, "minor", "2027-02-15", "2027-02-21", 100, "Arithmetic Logic Unit implemented and simulated in synthesizable RTL.", "Verilog"),
            ("SEM4-M5", "Passive AM/FM Receiver PCB", 4, "minor", "2027-03-01", "2027-03-14", 100, "RF resonant tank circuit layout and analog tuning stage.", "KiCad, Analog RF"),
            ("SEM4-M6", "ARM GPIO Store LED Matrix", 4, "minor", "2027-03-15", "2027-03-28", 100, "Bare-metal DMA-driven display controller on ARM Cortex.", "C, ARM STM32"),
            ("SEM4-MAJ1", "FPGA Hardware Smart Scale", 4, "major", "2027-01-10", "2027-02-14", 200, "High-frequency ADC sampling and hardware filtering pipeline on FPGA.", "Verilog, FPGA"),
            ("SEM4-MAJ2", "IoT Warehouse Grid System", 4, "major", "2027-03-01", "2027-04-04", 200, "Distributed multi-node tracking over localized RF communication mesh.", "C++, LoRa"),
            ("SEM4-MAJ3", "Automated Checkout Gate", 4, "major", "2027-03-22", "2027-04-18", 200, "Integrated motorized access barrier responding to transaction events.", "C++, PID Control"),

            # SEMESTER 5
            ("SEM5-M1", "Store WiFi Dipole Antenna", 5, "minor", "2027-06-20", "2027-07-04", 100, "2.4 GHz tuned microstrip feed layout and impedance matching.", "HFSS, RF Layout"),
            ("SEM5-M2", "RFID Smart Cart Reader", 5, "minor", "2027-07-05", "2027-07-18", 100, "Anti-collision inventory scanner module reading multi-tag baskets.", "C, SPI Protocol"),
            ("SEM5-M3", "8086 Assembly Billing Logic", 5, "minor", "2027-07-19", "2027-08-01", 100, "Low-level interrupt-driven register routines for billing math.", "x86 Assembly"),
            ("SEM5-M4", "QNX RTOS Task Scheduler", 5, "minor", "2027-08-02", "2027-08-15", 100, "Hard real-time deterministic thread priorities and messaging.", "C, QNX"),
            ("SEM5-M5", "Basic AM Modulator Circuit", 5, "minor", "2027-08-16", "2027-08-29", 100, "Carrier mixing and signal envelope detection bench test.", "Analog Circuit Design"),
            ("SEM5-M6", "Wireless Sensor Node (BLE)", 5, "minor", "2027-08-30", "2027-09-12", 100, "Ultra low-power beacon broadcasting telemetry packets via BLE GATT.", "C, BLE"),
            ("SEM5-MAJ1", "Edge Vision Pricing Engine", 5, "major", "2027-06-20", "2027-07-25", 250, "Real-time shelf item recognition updating electronic price tags.", "OpenCV, Python"),
            ("SEM5-MAJ2", "SDR Retail Ads Broadcaster", 5, "major", "2027-08-02", "2027-09-05", 250, "Software-defined radio baseband modulation on USRP/HackRF.", "GNURadio, SDR"),

            # SEMESTER 6
            ("SEM6-M1", "CMOS Inverter Layout", 6, "minor", "2028-01-03", "2028-01-16", 100, "Silicon layout, DRC/LVS verification, and parasitic extraction.", "Magic, VLSI"),
            ("SEM6-M2", "VLAN & POS Secure Network", 6, "minor", "2028-01-17", "2028-01-30", 100, "802.1Q isolated subnets and firewall packet filtering.", "Networking, Cisco IOS"),
            ("SEM6-M3", "RSA Encryption for POS", 6, "minor", "2028-01-31", "2028-02-13", 100, "Asymmetric public-key cryptographic engine with key rotation.", "Python, Cryptography"),
            ("SEM6-M4", "JPEG Image Compression", 6, "minor", "2028-02-14", "2028-02-20", 100, "Discrete Cosine Transform (DCT) and quantization algorithm in C.", "C, Signal Processing"),
            ("SEM6-M5", "DSP Audio Ambience Control", 6, "minor", "2028-02-28", "2028-03-12", 100, "Real-time acoustic noise cancellation and equalization filter.", "MATLAB, C"),
            ("SEM6-M6", "16-bit Carry Lookahead Adder", 6, "minor", "2028-03-13", "2028-03-26", 100, "Synthesizable high-speed parallel prefix adder logic.", "Verilog"),
            ("SEM6-MAJ1", "Unified Retail ERP Platform", 6, "major", "2028-01-03", "2028-02-13", 250, "Central coordination hub tying point-of-sale to accounting.", "FastAPI, React"),
            ("SEM6-MAJ2", "Smart Warehouse Drone Node", 6, "major", "2028-02-28", "2028-04-02", 250, "Autonomous aerial optical scanner checking high-shelf barcodes.", "Python, ROS"),

            # SEMESTER 7
            ("SEM7-M1", "Microwave Waveguide Sim", 7, "minor", "2028-06-18", "2028-07-02", 100, "Electromagnetic finite-element boundary simulation.", "HFSS, Python"),
            ("SEM7-M2", "SystemVerilog Arbiter", 7, "minor", "2028-07-03", "2028-07-16", 100, "Round-robin bus arbiter with assertion-based verification (SVA).", "SystemVerilog"),
            ("SEM7-M3", "PID Controller for Doors", 7, "minor", "2028-07-17", "2028-07-30", 100, "Closed-loop feedback algorithm controlling DC servo entrance actuators.", "C, PID Control"),
            ("SEM7-M4", "AXI Protocol Simulator", 7, "minor", "2028-08-01", "2028-08-13", 100, "AXI4-Lite master/slave burst handshake transaction verification.", "SystemVerilog"),
            ("SEM7-M5", "SDN Routing for Multi-Branch", 7, "minor", "2028-08-14", "2028-08-27", 100, "OpenFlow software-defined WAN routing between store facilities.", "Python, SDN"),
            ("SEM7-M6", "Placement Vault Dashboard", 7, "minor", "2028-08-28", "2028-09-10", 100, "Executive recruitment analytics portfolio interface.", "React, FastAPI"),
            ("SEM7-MAJ1", "Automated Conveyor System", 7, "major", "2028-06-18", "2028-07-23", 250, "PLC/Microcontroller multi-tier sorter with optical sensors.", "C++, PLC Ladder"),
            ("SEM7-MAJ2", "Zynq SoC Retail Terminal", 7, "major", "2028-08-01", "2028-09-10", 300, "Heterogeneous ARM + FPGA SoC running Linux with hardware acceleration.", "C, Verilog")
        ]
        c.executemany("""
            INSERT INTO roadmap_milestones (code, title, semester, tier, start_date, end_date, xp_reward, description, tech_stack)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, curriculum)

    conn.commit()
    conn.close()

init_database()

# ==============================================================================
# FastAPI App Setup
# ==============================================================================
app = FastAPI(title="ECE Portfolio Command Center", version="2.0")

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
    current_semester: Optional[int] = 3

class QuestSubmitRequest(BaseModel):
    quest_id: int
    submission_url: Optional[str] = ""
    notes: Optional[str] = ""

class MessageSendRequest(BaseModel):
    receiver_id: int
    content: str

# ==============================================================================
# Helpers & Auth Dependencies
# ==============================================================================
def get_active_academic_semester() -> int:
    today = date.today().isoformat()
    if today < "2027-01-03":
        return 3
    elif today < "2027-06-20":
        return 4
    elif today < "2028-01-03":
        return 5
    elif today < "2028-06-18":
        return 6
    else:
        return 7

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required.")

    username = authorization.split("Bearer ", 1)[1].strip()
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, username, role, current_xp, current_semester FROM users WHERE LOWER(username) = LOWER(?);", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid session credentials.")
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
        c.execute("SELECT id, username, role, current_xp, current_semester FROM users WHERE LOWER(username) = LOWER(?);", (username,))
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
        if not user:
            raise HTTPException(status_code=401, detail="Invalid callsign or credentials.")

        user_dict = dict(user)
        if not verify_password(user_dict.get("password_hash"), payload.password):
            raise HTTPException(status_code=401, detail="Invalid callsign or credentials.")

        user_dict.pop("password_hash", None)
        return {"status": "success", "user": user_dict}
    finally:
        conn.close()

@app.post("/api/auth/register")
def auth_register(payload: RegisterRequest):
    username = payload.username.strip().lower()
    password = payload.password.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Callsign cannot be empty.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Passphrase must be at least 4 characters.")

    # Guard: prevent overriding or registering creator account
    if username == "ganshyam":
        raise HTTPException(status_code=403, detail="The master creator callsign is restricted. Please login.")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE LOWER(username) = ?;", (username,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Callsign already taken. Please choose another.")

        pw_hash = hash_password(password)
        # CRITICAL ENFORCEMENT: Force role to 'member' permanently
        c.execute("""
            INSERT INTO users (username, password_hash, role, current_xp, current_semester)
            VALUES (?, ?, 'member', 100, ?);
        """, (username, pw_hash, payload.current_semester or 3))
        conn.commit()

        c.execute("SELECT id, username, role, current_xp, current_semester FROM users WHERE LOWER(username) = ?;", (username,))
        return {"status": "success", "user": dict(c.fetchone())}
    finally:
        conn.close()

# ==============================================================================
# Feature Routes
# ==============================================================================
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

@app.get("/api/quests")
def get_quests(semester: Optional[int] = None, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        current_active = get_active_academic_semester()
        target_sem = semester if semester is not None else current_active
        user_id = user["id"] if user else 0

        c.execute("""
            SELECT 
                m.id,
                m.code,
                m.title,
                m.description,
                m.semester,
                m.tier,
                m.start_date,
                m.end_date,
                m.xp_reward,
                m.tech_stack,
                COALESCE(p.status, 'PENDING') AS status,
                p.repo_url,
                p.submitted_at
            FROM roadmap_milestones m
            LEFT JOIN user_quest_progress p 
                   ON m.id = p.quest_id AND p.user_id = ?
            WHERE m.semester = ?
            ORDER BY m.start_date ASC, m.id ASC;
        """, (user_id, target_sem))

        quests = [dict(r) for r in c.fetchall()]
        today = date.today()
        previous_completed = True

        for q in quests:
            is_done = q["status"] in ("SUBMITTED", "COMPLETED")

            if q.get("end_date"):
                try:
                    end_d = date.fromisoformat(q["end_date"])
                    q["days_remaining"] = (end_d - today).days
                except Exception:
                    q["days_remaining"] = 999
            else:
                q["days_remaining"] = 999

            if not previous_completed:
                q["status"] = "LOCKED"
            elif not is_done:
                previous_completed = False

        return {
            "current_active_semester": current_active,
            "selected_semester": target_sem,
            "quests": quests
        }
    finally:
        conn.close()

@app.post("/api/quests/submit")
def submit_quest(payload: QuestSubmitRequest, user: dict = Depends(get_current_user)):
    if not payload.submission_url.strip() and not payload.notes.strip():
        raise HTTPException(status_code=400, detail="Provide a valid artifact/repository URL or notes.")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, title, xp_reward FROM roadmap_milestones WHERE id = ?;", (payload.quest_id,))
        quest = c.fetchone()
        if not quest:
            raise HTTPException(status_code=404, detail="Milestone quest not found.")

        xp_to_award = quest["xp_reward"] if quest["xp_reward"] else 100

        c.execute("""
            INSERT INTO user_quest_progress (user_id, quest_id, repo_url, notes, status, submitted_at)
            VALUES (?, ?, ?, ?, 'SUBMITTED', CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, quest_id) DO UPDATE SET
                repo_url = excluded.repo_url,
                notes = excluded.notes,
                status = 'SUBMITTED',
                submitted_at = CURRENT_TIMESTAMP;
        """, (user["id"], payload.quest_id, payload.submission_url.strip(), payload.notes.strip()))

        c.execute("UPDATE users SET current_xp = current_xp + ? WHERE id = ?;", (xp_to_award, user["id"]))
        conn.commit()

        return {"status": "success", "message": f"Quest '{quest['title']}' submitted! +{xp_to_award} XP allocated."}
    finally:
        conn.close()

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
        c.execute("""
            INSERT INTO private_messages (sender_id, receiver_id, content)
            VALUES (?, ?, ?);
        """, (user["id"], payload.receiver_id, payload.content.strip()))
        conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

# ==============================================================================
# Static File Hosting
# ==============================================================================
if os.path.exists(FRONTEND_DIR):
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend_dir")
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend_root")

@app.get("/")
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "ECE Portfolio Command Center API active."}