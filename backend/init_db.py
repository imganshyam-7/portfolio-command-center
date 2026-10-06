import sqlite3
import hashlib
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "command_center.db"

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        github_username TEXT UNIQUE NOT NULL,
        registered_device_id TEXT,
        face_registered INTEGER DEFAULT 0,
        hp INTEGER DEFAULT 100,
        max_hp INTEGER DEFAULT 100,
        current_xp INTEGER DEFAULT 0,
        current_semester INTEGER DEFAULT 3,
        avatar_color TEXT DEFAULT '#7c3aed'
    );
    """)

    # 2. Reference Facial Biometrics
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_faces (
        user_id INTEGER PRIMARY KEY,
        face_encoding BLOB NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # 3. Master Quests with Code Verification Signatures
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        semester INTEGER NOT NULL,
        title TEXT NOT NULL,
        cadence_type TEXT NOT NULL,
        polish_tag TEXT NOT NULL,
        domain TEXT NOT NULL,
        is_group_project INTEGER DEFAULT 0,
        start_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        base_xp INTEGER NOT NULL,
        required_repo_name TEXT NOT NULL,
        required_extensions TEXT NOT NULL, -- Comma-separated: '.py,.html'
        required_keywords TEXT NOT NULL    -- Comma-separated: 'fastapi,uvicorn,sqlite'
    );
    """)

    # 4. User Quest Progress
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_quest_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_id INTEGER NOT NULL,
        status TEXT DEFAULT 'PENDING',
        submitted_repo_url TEXT,
        verified_device_id TEXT,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (quest_id) REFERENCES roadmap_milestones(id),
        UNIQUE(user_id, quest_id)
    );
    """)

    # 5. Pod Allocations
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pod_allocations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quest_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        pod_name TEXT NOT NULL,
        role_title TEXT NOT NULL,
        FOREIGN KEY (quest_id) REFERENCES roadmap_milestones(id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(quest_id, user_id)
    );
    """)

    # 6. Academic Schedule
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS academic_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        semester INTEGER NOT NULL,
        event_name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        freeze_active INTEGER DEFAULT 1
    );
    """)

    # Seed Default Users
    cursor.execute("DELETE FROM users;")
    seed_users = [
        ("ganshyam", hash_pw("admin123"), "Ganshyam (Architect)", "creator", "imganshyam-7", None, 100, 100, 350, 3, "#7c3aed"),
        ("rohit", hash_pw("user123"), "Rohit Kumar", "member", "rohit-ece", None, 100, 100, 150, 3, "#2563eb"),
        ("sneha", hash_pw("user123"), "Sneha Reddy", "member", "sneha-dev", None, 100, 100, 200, 3, "#db2777"),
        ("arjun", hash_pw("user123"), "Arjun Varma", "member", "arjun-embedded", None, 100, 100, 100, 3, "#ea580c")
    ]
    cursor.executemany("""
        INSERT INTO users (username, password_hash, full_name, role, github_username, registered_device_id, hp, max_hp, current_xp, current_semester, avatar_color)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, seed_users)

    # Seed Quests with Strict Verification Signatures
    cursor.execute("DELETE FROM roadmap_milestones;")
    quests = [
        (3, "Portfolio Command Center (FastAPI + DB)", "Minor 1", "Underwater", "Full-Stack Web", 0, "2026-10-01", "2026-10-18", 300, "portfolio-command-center", ".py,.html,.css", "fastapi,uvicorn,sqlite3"),
        (3, "OpenCV QR & Barcode Scanner", "Minor Quest", "🎯 Minor (Optical POS)", "Computer Vision", 0, "2026-10-07", "2026-10-18", 350, "opencv-qr-barcode-scanner", ".py", "cv2,qrcodedetector,barcode,imshow"),
        (3, "B2B Wholesale Data Scraper (Python)", "Minor 2", "🎯 Minor 1 (Retail)", "Automation / Data", 0, "2026-10-07", "2026-10-20", 350, "b2b-wholesale-scraper", ".py", "requests,bs4,scrape,soup"),
        (3, "OpenCV Body/Face Recog Module Tests", "Minor 3", "Underwater", "Computer Vision", 0, "2026-10-21", "2026-11-01", 300, "opencv-face-recog", ".py", "cv2,cascade,face,detectmultiscale"),
        (3, "AM Crystal Radio Circuit Simulation", "Minor 4", "Underwater", "Analog Simulation", 0, "2026-12-01", "2026-12-13", 250, "am-crystal-radio-sim", ".py,.cir,.asc", "diode,tank,frequency,carrier"),
        (3, "Single-Chip FM Receiver Simulation", "Minor 5", "Underwater", "RF / Analog EDA", 0, "2026-12-14", "2026-12-20", 250, "fm-receiver-sim", ".py,.cir,.asc", "demodulator,oscillator,audio"),
        (3, "Basic Python Sales Data Parser", "Minor 6", "Underwater", "Software / POS", 0, "2026-12-21", "2026-12-27", 300, "sales-data-parser", ".py,.csv,.json", "pandas,csv,parse,sales"),
        (3, "DSP Audio Filter Simulation (MATLAB/Python)", "Major 1", "Underwater", "DSP", 0, "2026-12-28", "2027-01-03", 500, "dsp-audio-filter-sim", ".py,.m", "scipy,numpy,butter,filter,fft"),
        (3, "Automated Invoice OCR Generator (Group of 3)", "Major 2", "Underwater", "OCR & Systems", 1, "2027-01-04", "2027-01-15", 550, "invoice-ocr-generator", ".py", "pytesseract,cv2,ocr,invoice")
    ]
    cursor.executemany("""
        INSERT INTO roadmap_milestones 
        (semester, title, cadence_type, polish_tag, domain, is_group_project, start_date, deadline, base_xp, required_repo_name, required_extensions, required_keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, quests)

    # Seed Pod Assignments
    cursor.execute("DELETE FROM pod_allocations;")
    pod_assignments = [
        (9, 1, "Pod B (Middleware/Systems)", "Integration Lead & Pipeline Architect"),
        (9, 2, "Pod A (Firmware/RTL)", "Pre-processing & Text Binarization Engine"),
        (9, 3, "Pod C (Verification/UI)", "OCR Layout Parsing & Telemetry Verification")
    ]
    cursor.executemany("""
        INSERT INTO pod_allocations (quest_id, user_id, pod_name, role_title)
        VALUES (?, ?, ?, ?);
    """, pod_assignments)

    # Seed Academic Calendar Freezes
    cursor.execute("DELETE FROM academic_schedule;")
    cursor.execute("""
        INSERT INTO academic_schedule (semester, event_name, start_date, end_date, freeze_active)
        VALUES (3, 'ACADEMIC FREEZE: CIE-2 Internals', '2026-11-23', '2026-11-28', 1),
               (3, 'ACADEMIC FREEZE: Theory & Lab SEE', '2026-11-30', '2027-01-02', 1);
    """)

    conn.commit()
    conn.close()
    print("[OK] Schema updated with code-verification signatures.")

if __name__ == "__main__":
    init_database()