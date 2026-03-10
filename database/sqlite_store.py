"""SQLite persistence layer for users, knowledge map, study plans, and question records."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class StudyPlanItem:
    question_id: str
    scheduled_date: str
    completed: int


class SQLiteStore:
    """Simple SQLite repository with explicit schema management."""

    def __init__(self, db_path="sql_tutor.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    user_metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS knowledge_map (
                    user_id TEXT,
                    topic TEXT,
                    confidence_score REAL,
                    PRIMARY KEY (user_id, topic)
                );

                CREATE TABLE IF NOT EXISTS study_plan (
                    user_id TEXT,
                    question_id TEXT,
                    scheduled_date TEXT,
                    completed INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, question_id)
                );

                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    question_json TEXT,
                    status TEXT,
                    created_at TEXT
                );
                """
            )
            conn.commit()

    def upsert_user(self, user_id, user_metadata):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(user_id, user_metadata)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET user_metadata=excluded.user_metadata
                """,
                (user_id, json.dumps(user_metadata)),
            )
            conn.commit()

    def save_question(self, question_id, user_id, question_json, status):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO questions(question_id, user_id, question_json, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (question_id, user_id, json.dumps(question_json), status, datetime.utcnow().isoformat()),
            )
            conn.commit()

    def get_questions(self, user_id, status=None):
        query = "SELECT * FROM questions WHERE user_id=?"
        params = [user_id]
        if status:
            query += " AND status=?"
            params.append(status)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) | {"question_json": json.loads(row["question_json"])} for row in rows]

    def mark_question_status(self, question_id, status):
        with self._connect() as conn:
            conn.execute("UPDATE questions SET status=? WHERE question_id=?", (status, question_id))
            conn.commit()

    def update_knowledge(self, user_id, topic, confidence_score):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_map(user_id, topic, confidence_score)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, topic) DO UPDATE SET confidence_score=excluded.confidence_score
                """,
                (user_id, topic, confidence_score),
            )
            conn.commit()

    def get_knowledge_map(self, user_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT topic, confidence_score FROM knowledge_map WHERE user_id=? ORDER BY topic", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_study_item(self, user_id, question_id, scheduled_date, completed=0):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO study_plan(user_id, question_id, scheduled_date, completed)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, question_id)
                DO UPDATE SET scheduled_date=excluded.scheduled_date, completed=excluded.completed
                """,
                (user_id, question_id, scheduled_date, completed),
            )
            conn.commit()

    def get_study_plan(self, user_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT question_id, scheduled_date, completed FROM study_plan WHERE user_id=? ORDER BY scheduled_date",
                (user_id,),
            ).fetchall()
        return [StudyPlanItem(**dict(row)) for row in rows]

    def mark_study_completed(self, user_id, question_id):
        with self._connect() as conn:
            conn.execute(
                "UPDATE study_plan SET completed=1 WHERE user_id=? AND question_id=?",
                (user_id, question_id),
            )
            conn.commit()
