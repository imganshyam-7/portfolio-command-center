import os
import sqlite3
import hashlib
import secrets
import json
from datetime import date, datetime
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.biometrics import extract_face_embedding, verify_faces

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
# Ensure legacy NOT NULL columns do not block registration
    c.execute("PRAGMA table_info(users);")
    existing_cols = [r[1] for r in c.fetchall()]
    for legacy_col in ["full_name", "email"]:
        if legacy_col in existing_cols:
            try:
                c.execute(f"ALTER TABLE users DROP COLUMN {legacy_col};")
                print(f"[DB MIGRATION] Dropped obsolete column '{legacy_col}' from table 'users'.")
            except Exception as e:
                print(f"[DB WARNING] Failed to drop '{legacy_col}': {e}")
    # 1. Base Users Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            biometric_encoding TEXT,
            role TEXT DEFAULT 'member',
            current_xp INTEGER DEFAULT 0,
            current_semester INTEGER DEFAULT 3,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Self-healing column patch for users table
    c.execute("PRAGMA table_info(users);")
    user_cols = [r[1] for r in c.fetchall()]
    user_patches = [
        ("biometric_encoding", "TEXT"),
        ("current_xp", "INTEGER DEFAULT 0"),
        ("current_semester", "INTEGER DEFAULT 3"),
        ("role", "TEXT DEFAULT 'member'")
    ]
    for col, definition in user_patches:
        if col not in user_cols:
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition};")
                print(f"[DB MIGRATION] Added column '{col}' to table 'users'.")
            except Exception as e:
                print(f"[DB WARNING] Failed patching '{col}': {e}")

    # Seed Creator Account if Missing
    c.execute("SELECT id FROM users WHERE LOWER(username) = 'ganshyam';")
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (username, password_hash, role, current_xp, current_semester)
            VALUES ('ganshyam', ?, 'creator', 0, 3);
        """, (hash_password("ganshyam123"),))

    # 2. Quest Progress Table & Migrations
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
                print(f"[DB MIGRATION] Added column '{col}' to table 'user_quest_progress'.")
            except Exception as e:
                print(f"[DB WARNING] Failed patching '{col}': {e}")

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
            tech_stack TEXT,
            cadence_type TEXT DEFAULT 'sprint',
            required_repo_name TEXT DEFAULT 'pending-repo',
            polish_tag TEXT DEFAULT 'standard',
            domain TEXT DEFAULT 'ECE'
        );
    """)

    c.execute("SELECT COUNT(*) FROM roadmap_milestones;")
    if c.fetchone()[0] == 0:
        curriculum = [
            # SEMESTER 3
            ("SEM3-M1", "B2B Procurement Scraper", 3, "minor", "2026-10-19", "2026-10-25", 100, 
             "Architect and deploy an automated B2B procurement scraping engine leveraging Python, Playwright, and BeautifulSoup. The system navigates dynamic wholesale marketplaces (such as IndiaMART or Alibaba), bypassing client-side rendering bottlenecks and rate limits to extract structured product tiers, wholesale lot pricing, and supplier credential verifications. Captured telemetry is normalized, deduplicated, and persistently archived into SQLite with transaction logging, enabling downstream price-trend analysis and automated re-ordering pipelines.",
             "Python, Playwright, BeautifulSoup, SQLite"),
            ("SEM3-M2", "OpenCV Face/Body Recog Base", 3, "minor", "2026-10-26", "2026-11-01", 100,
             "Construct a baseline computer vision surveillance pipeline in C++ and Python utilizing OpenCV with lightweight ONNX neural network backends (YuNet and SFace). The pipeline ingests live video streams from connected webcam hardware, performs real-time face detection with landmark alignment, extracts 128-dimensional biometric embeddings, and executes cosine similarity matching against local facial rosters to prevent proxy check-ins and unauthorized terminal access.",
             "Python, C++, OpenCV, ONNX"),
            ("SEM3-M3", "Retail Footfall Counter", 3, "minor", "2026-11-02", "2026-11-08", 100,
             "Develop an optical retail footfall monitoring engine that tracks pedestrian vector trajectories across predefined directional boundary planes. Utilizing OpenCV background subtraction (MOG2) paired with centroid tracking algorithms in NumPy, the engine filters out environmental noise, tracks individual movement vectors, and logs bidirectional foot traffic metrics into a structured telemetry database for peak-hour retail density analysis.",
             "OpenCV, NumPy, Python"),
            ("SEM3-M4", "Digital Signal Filter Sim", 3, "minor", "2026-11-09", "2026-11-15", 100,
             "Implement a digital signal processing simulation suite in Python leveraging NumPy and SciPy to design, analyze, and test Finite Impulse Response (FIR) and Infinite Impulse Response (IIR) digital filters. The system computes transfer functions, generates pole-zero plots, and analyzes frequency responses using Fast Fourier Transforms (FFT) across synthetic noisy audio feeds, verifying phase linearity and stopband attenuation characteristics.",
             "Python, SciPy, NumPy, Matplotlib"),
            ("SEM3-M5", "Local Inventory Sync Script", 3, "minor", "2026-11-16", "2026-11-22", 100,
             "Engineer an offline-first relational database synchronization daemon for POS registers operating in constrained network environments. Built with Python and SQLite running in Write-Ahead Logging (WAL) mode, the daemon batches local register sales and transaction logs into signed JSON payloads, executes idempotent delta reconciliations against a central master endpoint upon network restoration, and handles distributed conflict resolution seamlessly.",
             "Python, SQLite, REST APIs"),
            ("SEM3-MAJ1", "Smart Retail POS Terminal", 3, "major", "2026-10-11", "2026-11-08", 200,
             "Design and deliver a production-ready Smart Retail Point-of-Sale (POS) terminal integrating a high-performance FastAPI asynchronous backend with a responsive retro-styled tactical web dashboard. The terminal manages real-time SKU barcode lookups, persistent cart state, atomic inventory decrements, thermal receipt payload generation, and localized sales reporting while maintaining low latency under peak store throughput.",
             "FastAPI, JavaScript, SQLite, HTML5/CSS3"),
            ("SEM3-MAJ2", "STM32 Ethernet Bootloader", 3, "major", "2026-10-26", "2026-11-22", 200,
             "Develop an embedded Ethernet bootloader firmware application for ARM Cortex-M microcontrollers (STM32 series) programmed in bare-metal C. The bootloader interfaces directly with physical Ethernet MAC/PHY controllers, listens for incoming UDP/TFTP flash firmware packets, validates cyclic redundancy checksums (CRC32), and safely reprograms target internal flash memory sectors while supporting automated rollback in the event of transmission failure.",
             "Embedded C, ARM Cortex-M, STM32, Ethernet"),

            # SEMESTER 4
            ("SEM4-M1", "I2C Store Climate Sensor", 4, "minor", "2027-01-03", "2027-01-17", 100,
             "Design a custom Linux kernel I2C bus driver and telemetry daemon for industrial ambient sensors monitoring store room climate. The software establishes reliable communication over I2C register maps, samples temperature and relative humidity at deterministic intervals, implements rolling hardware averaging to filter transient spikes, and exposes data through standardized sysfs endpoints.",
             "C, Linux Kernel Drivers, I2C"),
            ("SEM4-M2", "Stepper Motor Conveyor Ctrl", 4, "minor", "2027-01-18", "2027-01-31", 100,
             "Program a deterministic FreeRTOS stepper motor controller running on an STM32 microcontroller to drive warehouse conveyor sorting belts. The firmware executes trapezoidal acceleration/deceleration speed profiles, synchronizes step timing via hardware timers with sub-millisecond jitter, and integrates optical home limit switches with emergency-stop hardware interrupts.",
             "C++, FreeRTOS, STM32, Timers"),
            ("SEM4-M3", "Edge AI Surveillance Node", 4, "minor", "2027-02-01", "2027-02-14", 100,
             "Deploy an edge-accelerated surveillance inference node utilizing Google Coral EdgeTPU silicon integrated with Python and OpenCV. The node ingests RTSP surveillance feeds, executes quantized MobileNet SSD object detection pipelines locally without sending video streams to the cloud, and broadcasts localized bounding box coordinates over encrypted MQTT message brokers.",
             "Python, EdgeTPU, OpenCV, MQTT"),
            ("SEM4-M4", "Verilog ALU Design", 4, "minor", "2027-02-15", "2027-02-21", 100,
             "Implement an Arithmetic Logic Unit (ALU) modeled in synthesizable IEEE 1364 Verilog RTL. The module performs multi-bit integer arithmetic, boolean logic, bitwise shifting, and condition code flag generation, supported by a self-checking testbench run through ModelSim/Icarus Verilog.",
             "Verilog RTL, Icarus Verilog, GTKWave"),
            ("SEM4-M5", "Passive AM/FM Receiver PCB", 4, "minor", "2027-03-01", "2027-03-14", 100,
             "Design, simulate, and lay out an analog AM/FM radio receiver PCB in KiCad. The board features resonant LC tank circuits, high-frequency envelope detection diodes, low-noise audio amplification stages, and controlled microstrip trace impedance for RF signal paths.",
             "KiCad, Analog RF, SPICE Simulation"),
            ("SEM4-M6", "ARM GPIO Store LED Matrix", 4, "minor", "2027-03-15", "2027-03-28", 100,
             "Develop bare-metal C display driver firmware for a high-density LED matrix panel powered by ARM Cortex-M microcontrollers. The firmware utilizes Direct Memory Access (DMA) channels to stream framebuffer contents with zero CPU overhead, achieving tear-free visual refreshes.",
             "C, ARM Cortex-M, DMA, GPIO"),
            ("SEM4-MAJ1", "FPGA Hardware Smart Scale", 4, "major", "2027-01-10", "2027-02-14", 200,
             "Implement an FPGA-accelerated digital smart weighing scale designed in synthesizable Verilog RTL on Xilinx Artix-7 silicon. The hardware core interfaces with dual 24-bit delta-sigma ADCs via SPI, applies real-time finite impulse response filtering in hardware DSP slices, and computes weight taring and pricing arithmetic in single-cycle pipelines before driving an onboard display.",
             "Verilog RTL, FPGA, SPI, DSP Slices"),
            ("SEM4-MAJ2", "IoT Warehouse Grid System", 4, "major", "2027-03-01", "2027-04-04", 200,
             "Construct an IoT warehouse inventory mesh network utilizing low-power LoRa transceivers paired with C++ firmware. The system coordinates time-slotted channel hopping (TSCH) across localized warehouse grid zones, implements packet acknowledgments with payload encryption, and forwards asset proximity beacons to a central gateway.",
             "C++, LoRaWAN, Mesh Networking"),
            ("SEM4-MAJ3", "Automated Checkout Gate", 4, "major", "2027-03-22", "2027-04-18", 200,
             "Build a closed-loop automated optical entry/exit barrier control mechanism. Utilizing rotary optical encoders and DC motor PWM drivers, the controller applies PID closed-loop feedback routines to open and close security gates in response to valid POS transaction webhooks.",
             "C++, PID Control, PWM, Hardware Drivers")
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
app = FastAPI(title="ECE Portfolio Command Center", version="3.1")

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
    biometric_image: str

class CalibrateRequest(BaseModel):
    biometric_image: str

class QuestSubmitRequest(BaseModel):
    quest_id: int
    submission_url: str
    biometric_snapshot: str

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
# Auth & Biometrics Routes
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
            raise HTTPException(status_code=401, detail="Invalid callsign or passphrase.")

        user_dict = dict(user)
        if not verify_password(user_dict.get("password_hash"), payload.password):
            raise HTTPException(status_code=401, detail="Invalid callsign or passphrase.")

        user_dict.pop("password_hash", None)
        user_dict["has_biometrics"] = bool(user_dict.get("biometric_encoding"))
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
    if username == "ganshyam":
        raise HTTPException(status_code=403, detail="The master creator callsign is restricted. Please login.")

    try:
        embedding = extract_face_embedding(payload.biometric_image)
        embedding_json = json.dumps(embedding)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Biometric Calibration Error: {str(e)}")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM users WHERE LOWER(username) = ?;", (username,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Callsign already taken.")

        pw_hash = hash_password(password)
        # Grants 50 XP starting welcome bonus to all registered cadets
        c.execute("""
            INSERT INTO users (username, password_hash, biometric_encoding, role, current_xp, current_semester)
            VALUES (?, ?, ?, 'member', 50, ?);
        """, (username, pw_hash, embedding_json, payload.current_semester or 3))
        conn.commit()

        c.execute("SELECT id, username, role, current_xp, current_semester FROM users WHERE LOWER(username) = ?;", (username,))
        return {"status": "success", "user": dict(c.fetchone())}
    finally:
        conn.close()

@app.post("/api/bio/calibrate")
def calibrate_biometrics(payload: CalibrateRequest, user: dict = Depends(get_current_user)):
    """Enrolls or recalibrates biometric face embedding (Creator-only privilege)."""
    if user["role"] != "creator":
        raise HTTPException(status_code=403, detail="Access Denied: Only Creator can recalibrate biometrics.")

    try:
        embedding = extract_face_embedding(payload.biometric_image)
        embedding_json = json.dumps(embedding)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Facial Optical Scan Failed: {str(e)}")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE users SET biometric_encoding = ? WHERE id = ?;", (embedding_json, user["id"]))
        conn.commit()
        return {"status": "success", "message": f"Biometric master face enrolled for [{user['username'].upper()}]."}
    finally:
        conn.close()

# ==============================================================================
# Quests & Anti-Proxy Submission
# ==============================================================================
@app.get("/api/quests")
def get_quests(semester: Optional[int] = None, user: Optional[dict] = Depends(get_optional_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        target_sem = semester if semester is not None else 3
        user_id = user["id"] if user else 0

        # Inter-semester progression lock: semester > 3 requires all prior semester quests completed
        semester_locked = False
        if target_sem > 3:
            if user_id > 0:
                c.execute("""
                    SELECT COUNT(*) FROM roadmap_milestones m
                    LEFT JOIN user_quest_progress p ON m.id = p.quest_id AND p.user_id = ?
                    WHERE m.semester = ? AND (p.status IS NULL OR (p.status != 'SUBMITTED' AND p.status != 'COMPLETED'));
                """, (user_id, target_sem - 1))
                incomplete = c.fetchone()[0]
                if incomplete > 0:
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
    if not url:
        raise HTTPException(status_code=400, detail="Repository link cannot be empty.")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # Anti-Proxy Verification
    enrolled_encoding_str = user.get("biometric_encoding")
    if not enrolled_encoding_str:
        if user["role"] == "creator":
            raise HTTPException(
                status_code=400, 
                detail="Master Face Uncalibrated! Click '⚡ ENROLL CREATOR BIOMETRICS' in the top status bar first."
            )
        else:
            raise HTTPException(
                status_code=400, 
                detail="Biometric profile not enrolled. Contact Creator to initialize your node."
            )

    try:
        enrolled_embedding = json.loads(enrolled_encoding_str)
        is_match = verify_faces(enrolled_embedding, payload.biometric_snapshot)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Optical Biometric Error: {str(e)}")

    if not is_match:
        raise HTTPException(
            status_code=403, 
            detail="⛔ BIOMETRIC REJECTED: Verification failed. The live operator does not match the registered face for this account!"
        )

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, title, xp_reward FROM roadmap_milestones WHERE id = ?;", (payload.quest_id,))
        quest = c.fetchone()
        if not quest:
            raise HTTPException(status_code=404, detail="Milestone directive not found.")

        # Check existing submission to prevent duplicate XP inflation
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

        msg = f"Biometrics verified! Directive '{quest['title']}' submitted."
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

@app.get("/api/users")
def get_users(user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT id, username, role, current_xp, (biometric_encoding IS NOT NULL) AS has_bio FROM users ORDER BY id ASC;")
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