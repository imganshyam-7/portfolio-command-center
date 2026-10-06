import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "command_center.db"
FRONTEND_PATH = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="RPG Portfolio Command Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class QuestSubmission(BaseModel):
    repo_url: str

class InventoryAdjust(BaseModel):
    stock_quantity: int

# --- Player Stats & Semester Progression ---

@app.get("/api/player")
def get_player_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM player_stats WHERE id = 1;")
    player = dict(c.fetchone())
    conn.close()
    return player

# --- Academic Freeze Status ---

@app.get("/api/freeze-status")
def get_freeze_status():
    today = date.today().isoformat()
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT event_name FROM academic_schedule
        WHERE freeze_active = 1 AND ? BETWEEN start_date AND end_date
        LIMIT 1;
    """, (today,))
    active = c.fetchone()

    c.execute("""
        SELECT event_name, start_date FROM academic_schedule
        WHERE freeze_active = 1 AND start_date > ?
        ORDER BY start_date ASC
        LIMIT 1;
    """, (today,))
    next_ev = c.fetchone()
    conn.close()

    days_rem = None
    if next_ev:
        days_rem = (date.fromisoformat(next_ev["start_date"]) - date.fromisoformat(today)).days

    return {
        "current_date": today,
        "is_frozen": active is not None,
        "active_event": active["event_name"] if active else None,
        "next_freeze_event": next_ev["event_name"] if next_ev else None,
        "days_to_next_freeze": days_rem
    }

# --- Quests Management ---

@app.get("/api/quests")
def list_quests():
    today = date.today().isoformat()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT current_semester FROM player_stats WHERE id = 1;")
    current_sem = c.fetchone()["current_semester"]

    c.execute("""
        SELECT * FROM roadmap_milestones 
        WHERE semester = ? 
        ORDER BY deadline ASC;
    """, (current_sem,))
    quests = [dict(row) for row in c.fetchall()]

    # Annotate ongoing status dynamically by date
    for q in quests:
        if q["status"] == "COMPLETED":
            q["is_active_today"] = False
        else:
            q["is_active_today"] = (q["start_date"] <= today <= q["deadline"])

    conn.close()
    return quests

@app.post("/api/quests/{quest_id}/submit")
def submit_quest(quest_id: int, payload: QuestSubmission):
    today = date.today()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM roadmap_milestones WHERE id = ?;", (quest_id,))
    quest = c.fetchone()
    if not quest:
        conn.close()
        raise HTTPException(status_code=404, detail="Quest not found")

    if quest["status"] == "COMPLETED":
        conn.close()
        raise HTTPException(status_code=400, detail="Quest already completed!")

    # 1. Verification: Git link must match the quest slug
    expected_slug = quest["required_repo_name"].lower()
    submitted_url = payload.repo_url.strip().lower()

    if expected_slug not in submitted_url:
        conn.close()
        raise HTTPException(
            status_code=422,
            detail=f"Verification Failed! Repository URL must contain '{expected_slug}'. Provided: {payload.repo_url}"
        )

    # 2. XP & HP Gamification Calculation
    deadline_date = date.fromisoformat(quest["deadline"])
    days_diff = (deadline_date - today).days
    base_xp = quest["base_xp"]
    hp_penalty = 0

    if days_diff >= 0:
        # Completed on time or early: +15 XP bonus per early day (max +100 bonus)
        early_bonus = min(100, days_diff * 15)
        earned_xp = base_xp + early_bonus
        result_msg = f"Quest Complete! Earned {base_xp} Base XP + {early_bonus} Early-Bird Bonus XP!"
    else:
        # Overdue: 35% XP deduction and HP damage penalty
        days_late = abs(days_diff)
        earned_xp = max(50, int(base_xp * 0.65))
        hp_penalty = min(40, days_late * 5)
        result_msg = f"Quest Overdue by {days_late} days! Earned reduced {earned_xp} XP. Took -{hp_penalty} HP damage!"

    # 3. Update Quest Record
    c.execute("""
        UPDATE roadmap_milestones 
        SET status = 'COMPLETED', submitted_repo_url = ?, completed_at = ?
        WHERE id = ?;
    """, (payload.repo_url, today.isoformat(), quest_id))

    # 4. Update Player Stats
    c.execute("SELECT * FROM player_stats WHERE id = 1;")
    p = dict(c.fetchone())

    new_hp = max(1, p["hp"] - hp_penalty)
    new_xp = p["current_xp"] + earned_xp
    current_sem = p["current_semester"]
    leveled_up = False

    # Check if all quests of this semester are completed
    c.execute("""
        SELECT COUNT(*) as remaining FROM roadmap_milestones 
        WHERE semester = ? AND status != 'COMPLETED';
    """, (current_sem,))
    remaining_quests = c.fetchone()["remaining"]

    if remaining_quests == 0:
        # Level up to next semester!
        current_sem += 1
        new_hp = 100  # full heal on level-up
        new_xp += 1000  # 1000 Semester-Clear Bonus XP
        leveled_up = True
        rank_titles = {
            4: "Firmware Warlock (Sem 4)",
            5: "Edge Visionary (Sem 5)",
            6: "Distributed Architect (Sem 6)",
            7: "SoC Grandmaster (Sem 7)"
        }
        new_title = rank_titles.get(current_sem, f"Architect (Sem {current_sem})")
        c.execute("""
            UPDATE player_stats 
            SET current_semester = ?, hp = ?, current_xp = ?, xp_to_next_level = xp_to_next_level + 2000, rank_title = ?
            WHERE id = 1;
        """, (current_sem, new_hp, new_xp, new_title))
    else:
        c.execute("""
            UPDATE player_stats SET hp = ?, current_xp = ? WHERE id = 1;
        """, (new_hp, new_xp))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": result_msg,
        "earned_xp": earned_xp,
        "hp_penalty": hp_penalty,
        "leveled_up": leveled_up,
        "current_semester": current_sem
    }

# --- Inventory Endpoints ---

# @app.get("/api/inventory")
# def list_inventory():
#     conn = get_db()
#     c = conn.cursor()
#     c.execute("""
#         SELECT *, (retail_price - wholesale_cost) AS unit_margin,
#                ROUND(((retail_price - wholesale_cost) / retail_price) * 100, 2) AS margin_percentage
#         FROM retail_inventory
#         ORDER BY name ASC;
#     """)
#     rows = [dict(r) for r in c.fetchall()]
#     conn.close()
#     return rows

# @app.patch("/api/inventory/{sku}")
# def adjust_inventory(sku: str, payload: InventoryAdjust):
#     conn = get_db()
#     c = conn.cursor()
#     c.execute("UPDATE retail_inventory SET stock_quantity = ? WHERE sku = ?;", (payload.stock_quantity, sku))
#     conn.commit()
#     conn.close()
#     return {"sku": sku, "stock_quantity": payload.stock_quantity}

# --- Static Frontend Serving ---

app.mount("/static", StaticFiles(directory=FRONTEND_PATH), name="static")

@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_PATH / "index.html")