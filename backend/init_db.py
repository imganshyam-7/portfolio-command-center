import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "command_center.db"

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Player RPG Stats
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS player_stats (
        id INTEGER PRIMARY KEY,
        player_name TEXT DEFAULT 'Ganshyam',
        current_semester INTEGER DEFAULT 3,
        hp INTEGER DEFAULT 100,
        max_hp INTEGER DEFAULT 100,
        current_xp INTEGER DEFAULT 0,
        xp_to_next_level INTEGER DEFAULT 1800,
        rank_title TEXT DEFAULT 'Software Initiate (Sem 3)'
    );
    """)

    # 2. Academic Schedule & Freeze Windows (Across All Semesters)
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

    # 3. Master Roadmap Quests (Sem 3 to Sem 7)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roadmap_milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        semester INTEGER NOT NULL,
        title TEXT NOT NULL,
        cadence_type TEXT NOT NULL,     -- 'Minor 1'..'Minor 6', 'Major 1', 'Major 2'
        polish_tag TEXT NOT NULL,       -- 'Underwater', '🎯 Minor X', '🎯 Flagship X', '🎯 Specialized Capstone'
        domain TEXT NOT NULL,
        assigned_pod TEXT NOT NULL,
        start_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        base_xp INTEGER NOT NULL,
        required_repo_name TEXT NOT NULL,
        submitted_repo_url TEXT,
        status TEXT DEFAULT 'PENDING',
        completed_at TEXT
    );
    """)

    # Seed Player Profile
    cursor.execute("DELETE FROM player_stats;")
    cursor.execute("""
        INSERT INTO player_stats (id, player_name, current_semester, hp, max_hp, current_xp, xp_to_next_level, rank_title)
        VALUES (1, 'Ganshyam', 3, 100, 100, 250, 1800, 'Software Initiate (Sem 3)');
    """)

    # Seed All Academic Freeze Windows
    cursor.execute("DELETE FROM academic_schedule;")
    academic_freezes = [
        # Sem 3
        (3, "ACADEMIC FREEZE: Internals (Sem 3)", "2026-11-10", "2026-11-30", 1),
        (3, "Vasavi Theory & Lab SEE Window", "2026-12-01", "2027-01-02", 1),
        # Sem 4
        (4, "ACADEMIC FREEZE: Internals (Sem 4)", "2027-03-25", "2027-04-15", 1),
        (4, "Vasavi Sem 4 SEE Window", "2027-05-24", "2027-06-16", 1),
        # Sem 5
        (5, "ACADEMIC FREEZE: Internals (Sem 5)", "2027-09-01", "2027-09-30", 1),
        (5, "Vasavi Sem 5 SEE Window", "2027-12-10", "2028-01-02", 1),
        # Sem 6
        (6, "ACADEMIC FREEZE: Internals (Sem 6)", "2028-05-01", "2028-05-31", 1),
        (6, "Vasavi Sem 6 SEE Window", "2028-06-01", "2028-06-25", 1),
        # Sem 7
        (7, "ACADEMIC FREEZE: Internals (Sem 7)", "2028-09-01", "2028-09-30", 1),
        (7, "Vasavi Sem 7 Final Placements & SEE", "2028-12-05", "2028-12-31", 1)
    ]
    cursor.executemany("""
        INSERT INTO academic_schedule (semester, event_name, start_date, end_date, freeze_active)
        VALUES (?, ?, ?, ?, ?);
    """, academic_freezes)

    # Seed Master Quests (Sem 3 through Sem 7 1:1 with screenshots)
    cursor.execute("DELETE FROM roadmap_milestones;")
    master_roadmap = [
        # === SEMESTER 3 (Oct '26 - Jan '27): Software Foundations & DSP ===
        (3, "Portfolio Command Center (FastAPI + DB)", "Minor 1", "Underwater", "Full-Stack Web", "Pod B (Middleware/Systems)", "2026-10-01", "2026-10-18", 300, "portfolio-command-center"),
        (3, "B2B Wholesale Data Scraper (Python)", "Minor 2", "🎯 Minor 1 (Retail)", "Automation / Data", "Pod B (Middleware/Systems)", "2026-10-07", "2026-10-20", 350, "b2b-wholesale-scraper"),
        (3, "OpenCV Body/Face Recog Module Tests", "Minor 3", "Underwater", "Computer Vision", "Pod B (Middleware/Systems)", "2026-10-21", "2026-11-01", 300, "opencv-face-recog"),
        (3, "AM Crystal Radio Circuit Simulation", "Minor 4", "Underwater", "Analog Circuit Simulation", "Pod A (Firmware/RTL)", "2026-12-01", "2026-12-13", 250, "am-crystal-radio-sim"),
        (3, "Single-Chip FM Receiver Simulation", "Minor 5", "Underwater", "RF / Analog EDA", "Pod A (Firmware/RTL)", "2026-12-14", "2026-12-20", 250, "fm-receiver-sim"),
        (3, "Basic Python Sales Data Parser", "Minor 6", "Underwater", "Software / POS", "Pod B (Middleware/Systems)", "2026-12-21", "2026-12-27", 300, "sales-data-parser"),
        (3, "DSP Audio Filter Simulation (MATLAB/Python)", "Major 1", "Underwater", "Digital Signal Processing", "Pod C (Verification/UI)", "2026-12-28", "2027-01-03", 500, "dsp-audio-filter-sim"),
        (3, "Automated Invoice OCR Generator (Group of 3)", "Major 2", "Underwater", "Computer Vision & OCR", "Pod B (Middleware/Systems)", "2027-01-04", "2027-01-15", 550, "invoice-ocr-generator"),

        # === SEMESTER 4 (Jan '27 - Jun '27): Bare-Metal & Embedded Linux ===
        (4, "STM32 GPIO & UART Basic Comms", "Minor 1", "Underwater", "Bare-Metal Embedded C", "Pod A (Firmware/RTL)", "2027-01-20", "2027-02-07", 300, "stm32-gpio-uart"),
        (4, "STM32 Ethernet Bootloader", "Minor 2", "🎯 Minor 2 (Embedded)", "Firmware / Bootloader", "Pod A (Firmware/RTL)", "2027-02-08", "2027-02-21", 400, "stm32-ethernet-bootloader"),
        (4, "Linux Shell Scripting/Cron Automation (RPi)", "Minor 3", "Underwater", "Embedded Linux", "Pod B (Middleware/Systems)", "2027-02-22", "2027-03-07", 300, "rpi-cron-automation"),
        (4, "RPi Camera/Speaker Surveillance Sys.", "Minor 4", "🎯 Minor 3 (Edge HW)", "Edge Hardware Systems", "Pod B (Middleware/Systems)", "2027-03-08", "2027-03-21", 450, "rpi-surveillance-sys"),
        (4, "I2C/SPI Sensor Interfacing (STM32)", "Minor 5", "Underwater", "Embedded Protocols", "Pod A (Firmware/RTL)", "2027-04-16", "2027-04-25", 350, "stm32-i2c-spi-sensors"),
        (4, "RPi Audio Processing (ALSA/C++)", "Minor 6", "Underwater", "Systems Audio / C++", "Pod C (Verification/UI)", "2027-04-26", "2027-05-09", 350, "rpi-alsa-audio"),
        (4, "RTOS Task Scheduler built from scratch", "Major 1", "Underwater", "Real-Time OS Core", "Pod A (Firmware/RTL)", "2027-05-10", "2027-05-23", 550, "rtos-task-scheduler"),
        (4, "Smart Store Surveillance Sys (Group of 4)", "Major 2", "🎯 Flagship 1", "Edge AI & Vision Sys", "Pod B (Middleware/Systems)", "2027-05-24", "2027-06-13", 700, "smart-store-surveillance"),

        # === SEMESTER 5 (Jul '27 - Jan '28): IoT & High-Speed PCB ===
        (5, "555 Timer / Analog Sensor Circuit", "Minor 1", "Underwater", "Analog Electronics", "Pod A (Firmware/RTL)", "2027-07-20", "2027-08-01", 300, "555-analog-sensor"),
        (5, "Custom PCB Layout (KiCAD) for 555 Timer", "Minor 2", "Underwater", "PCB Design (KiCAD)", "Pod A (Firmware/RTL)", "2027-08-02", "2027-08-15", 350, "kicad-555-layout"),
        (5, "STM32 MQTT Client Setup", "Minor 3", "Underwater", "IoT Networking", "Pod B (Middleware/Systems)", "2027-08-16", "2027-08-29", 350, "stm32-mqtt-client"),
        (5, "STM32 IoT Retail Gateway to Cloud", "Minor 4", "🎯 Minor 4 (IoT)", "Cloud IoT Gateway", "Pod B (Middleware/Systems)", "2027-10-01", "2027-10-10", 450, "stm32-retail-gateway"),
        (5, "Digital Smart Scale Interface (Load Cell)", "Minor 5", "🎯 Minor 5 (Hardware)", "Industrial ADC / Sensors", "Pod A (Firmware/RTL)", "2027-10-11", "2027-10-24", 450, "smart-scale-interface"),
        (5, "ESP32 Wi-Fi Data Logger", "Minor 6", "Underwater", "Embedded Wireless", "Pod B (Middleware/Systems)", "2027-10-25", "2027-11-07", 350, "esp32-wifi-logger"),
        (5, "PCB Design of IoT Retail Gateway", "Major 1", "Underwater", "High-Speed PCB EDA", "Pod A (Firmware/RTL)", "2027-11-08", "2027-11-21", 550, "pcb-retail-gateway"),
        (5, "Edge CV Pipeline for Shelf Tracking (Group)", "Major 2", "Underwater", "Edge Computer Vision", "Pod B (Middleware/Systems)", "2027-11-22", "2027-12-05", 650, "shelf-tracking-cv"),

        # === SEMESTER 6 (Jan '28 - Jun '28): Verilog & Enterprise Systems ===
        (6, "TCP/IP Stack Implementation on STM32", "Minor 1", "Underwater", "Network Protocols (LwIP)", "Pod B (Middleware/Systems)", "2028-01-15", "2028-01-30", 400, "stm32-tcpip-stack"),
        (6, "FPGA Verilog Blink & Counters", "Minor 2", "Underwater", "Digital VLSI (Vivado)", "Pod A (Firmware/RTL)", "2028-01-31", "2028-02-13", 350, "verilog-blink-counters"),
        (6, "Verilog UART Controller Design", "Minor 3", "Underwater", "Digital VLSI (RTL)", "Pod A (Firmware/RTL)", "2028-02-14", "2028-03-12", 400, "verilog-uart-controller"),
        (6, "Automated Procurement Engine (Auto-orders)", "Minor 4", "🎯 Minor 6 (Software)", "B2B Automation / API", "Pod B (Middleware/Systems)", "2028-03-13", "2028-03-26", 450, "automated-procurement-engine"),
        (6, "Web Socket Dashboard for Live Hardware", "Minor 5", "Underwater", "Real-Time Telemetry", "Pod C (Verification/UI)", "2028-03-27", "2028-04-09", 400, "websocket-hardware-dashboard"),
        (6, "FreeRTOS Mutex/Semaphore Retail Sim", "Minor 6", "Underwater", "RTOS Concurrency", "Pod A (Firmware/RTL)", "2028-04-10", "2028-04-23", 400, "freertos-concurrency-sim"),
        (6, "Hardware-in-Loop (HIL) Testing Framework", "Major 1", "Underwater", "System Verification", "Pod C (Verification/UI)", "2028-04-24", "2028-05-14", 600, "hil-testing-framework"),
        (6, "Integrated Retail ERP System (Group of 5)", "Major 2", "🎯 Flagship 2", "Full-Stack Enterprise ERP", "Pod B (Middleware/Systems)", "2028-05-15", "2028-06-04", 800, "integrated-retail-erp"),

        # === SEMESTER 7 (Jul '28 - Dec '28): The Specialized Capstone ===
        (7, "ARM Cortex-M Assembly programming", "Minor 1", "Underwater", "ARM Low-Level ASM", "Pod A (Firmware/RTL)", "2028-07-15", "2028-07-30", 400, "arm-cortex-assembly"),
        (7, "Verilog SPI/I2C Cores", "Minor 2", "Underwater", "Synthesizable RTL IP", "Pod A (Firmware/RTL)", "2028-07-31", "2028-08-13", 450, "verilog-spi-i2c-cores"),
        (7, "Advanced PCB Routing (Diff Pairs, Lengths)", "Minor 3", "Underwater", "High-Speed EDA Routing", "Pod A (Firmware/RTL)", "2028-08-14", "2028-08-27", 450, "high-speed-pcb-routing"),
        (7, "Linux Device Drivers (Char driver)", "Minor 4", "Underwater", "Kernel Device Drivers", "Pod B (Middleware/Systems)", "2028-09-15", "2028-10-01", 500, "linux-char-driver"),
        (7, "Yocto Project Custom Linux Image", "Minor 5", "Underwater", "Embedded Build Systems", "Pod B (Middleware/Systems)", "2028-10-02", "2028-10-15", 500, "yocto-custom-linux"),
        (7, "Firmware OTA (Over-The-Air) Updater", "Minor 6", "Underwater", "Secure Boot & OTA", "Pod A (Firmware/RTL)", "2028-10-16", "2028-10-29", 500, "firmware-ota-updater"),
        (7, "FPGA Soft-Core Processor Implementation", "Major 1", "Underwater", "RISC-V / MicroBlaze SoC", "Pod A (Firmware/RTL)", "2028-10-30", "2028-11-12", 700, "fpga-softcore-processor"),
        (7, "Custom Hardware POS Terminal (Group)", "Major 2", "🎯 Specialized Capstone", "Industrial Hardware & OS", "Pod B (Middleware/Systems)", "2028-11-13", "2028-12-03", 1000, "custom-hardware-pos-terminal")
    ]

    cursor.executemany("""
        INSERT INTO roadmap_milestones 
        (semester, title, cadence_type, polish_tag, domain, assigned_pod, start_date, deadline, base_xp, required_repo_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING');
    """, master_roadmap)

    # Set Project 1 as IN_PROGRESS
    cursor.execute("UPDATE roadmap_milestones SET status = 'IN_PROGRESS' WHERE required_repo_name = 'portfolio-command-center';")

    conn.commit()
    conn.close()
    print("[OK] Master Blueprint (Sem 3 - Sem 7) successfully seeded into command_center.db!")

if __name__ == "__main__":
    init_database()