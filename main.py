from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3
import datetime
import os

app = FastAPI(title="Habit Tracker API")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "habits.db")

# Pydantic Models for Input Validation
class HabitCreate(BaseModel):
    name: str
    category: str
    description: Optional[str] = ""
    recurrence: Optional[str] = "daily"

class HabitLog(BaseModel):
    status: str # "Done", "Skipped", or "Missed"

# Database Initialization
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            recurrence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date DATE NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (habit_id) REFERENCES habits (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# API Endpoints
@app.post("/api/habits")
def create_habit(habit: HabitCreate):
    if not habit.name.strip():
        raise HTTPException(status_code=400, detail="Habit name is required")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO habits (name, category, description, recurrence) VALUES (?, ?, ?, ?)",
        (habit.name, habit.category, habit.description, habit.recurrence)
    )
    conn.commit()
    habit_id = cursor.lastrowid
    conn.close()
    return {"message": "Habit created successfully", "id": habit_id}

@app.get("/api/habits")
def get_habits():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM habits")
    habits = [dict(row) for row in cursor.fetchall()]
    
    today = datetime.date.today()
    first_day = today - datetime.timedelta(days=29)
    cursor.execute(
        "SELECT habit_id, log_date, status FROM habit_logs WHERE log_date BETWEEN ? AND ?",
        (first_day.isoformat(), today.isoformat()),
    )
    logs = {(row["habit_id"], row["log_date"]): row["status"] for row in cursor.fetchall()}
    conn.close()

    for habit in habits:
        habit["today_status"] = logs.get((habit["id"], today.isoformat()), "Pending")
        habit["history"] = [
            {
                "date": (first_day + datetime.timedelta(days=day)).isoformat(),
                "status": logs.get(
                    (habit["id"], (first_day + datetime.timedelta(days=day)).isoformat()),
                    "Pending",
                ),
            }
            for day in range(30)
        ]
        
    return habits

@app.post("/api/habits/{habit_id}/log")
def log_habit(habit_id: int, log: HabitLog):
    if log.status not in ["Done", "Skipped", "Missed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    today = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM habits WHERE id = ?", (habit_id,))
    if cursor.fetchone() is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Habit not found")
    
    # Check if already logged today
    cursor.execute("SELECT id FROM habit_logs WHERE habit_id = ? AND log_date = ?", (habit_id, today))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute("UPDATE habit_logs SET status = ? WHERE id = ?", (log.status, existing[0]))
    else:
        cursor.execute("INSERT INTO habit_logs (habit_id, log_date, status) VALUES (?, ?, ?)", 
                       (habit_id, today, log.status))
                       
    conn.commit()
    conn.close()
    return {"message": "Habit logged successfully"}

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    with open(os.path.join(BASE_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()