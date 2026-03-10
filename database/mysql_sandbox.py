"""SQLite-based sandbox for isolated per-user SQL execution with SELECT-only enforcement.

Note: kept in mysql_sandbox.py to minimize import churn in the app.
"""

import json
import os
import re
import sqlite3
import time

SELECT_ONLY_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE | re.DOTALL)
FORBIDDEN_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


class SQLSandboxError(Exception):
    """Raised when sandbox validation or execution fails."""


class MySQLSandbox:
    """Backwards-compatible sandbox class name, implemented with sqlite3."""

    def __init__(self):
        self.query_timeout_ms = int(os.getenv("QUERY_TIMEOUT_MS", "5000"))

    def _validate_query(self, query):
        if not SELECT_ONLY_RE.match(query) or FORBIDDEN_RE.search(query):
            raise SQLSandboxError("Only SELECT queries are allowed in the sandbox.")

    @staticmethod
    def _sqlite_type(declaration):
        decl = declaration.strip()
        if not decl:
            return "TEXT"

        parts = decl.split()
        column_name = parts[0]
        type_hint = " ".join(parts[1:]).upper() if len(parts) > 1 else "TEXT"

        if any(t in type_hint for t in ("INT", "TINYINT", "SMALLINT", "BIGINT")):
            mapped = "INTEGER"
        elif any(t in type_hint for t in ("REAL", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")):
            mapped = "REAL"
        elif "BLOB" in type_hint:
            mapped = "BLOB"
        else:
            mapped = "TEXT"

        return f'"{column_name}" {mapped}'

    def _load_dataset(self, conn, table_schema, table_data):
        cur = conn.cursor()
        for table, columns in table_schema.items():
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')
            sqlite_columns = ", ".join(self._sqlite_type(col) for col in columns)
            cur.execute(f'CREATE TABLE "{table}" ({sqlite_columns})')
            rows = table_data.get(table, [])
            if rows:
                placeholders = ", ".join(["?"] * len(rows[0]))
                cur.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
        conn.commit()

    def execute_query(self, user_id, query, table_schema, dataset):
        del user_id
        self._validate_query(query)

        conn = sqlite3.connect(":memory:")
        try:
            self._load_dataset(conn, table_schema, dataset)
            start = time.perf_counter()
            cur = conn.cursor()
            cur.execute(query)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if elapsed_ms > self.query_timeout_ms:
                raise SQLSandboxError(
                    f"Query exceeded timeout of {self.query_timeout_ms}ms (took {elapsed_ms}ms)."
                )
            columns = [c[0] for c in cur.description] if cur.description else []
            rows = cur.fetchall()
            return {"columns": columns, "rows": rows, "error": None}
        except sqlite3.Error as exc:
            return {"columns": [], "rows": [], "error": str(exc)}
        finally:
            conn.close()

    @staticmethod
    def compare_results(actual, expected):
        pass_fail = actual["columns"] == expected["columns"] and actual["rows"] == expected["rows"]
        return {
            "passed": pass_fail,
            "diff": None
            if pass_fail
            else json.dumps({"actual": actual, "expected": expected}, indent=2, default=str),
        }
