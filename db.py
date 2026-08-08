"""Camada de acesso ao Neon (Postgres). Sem ORM — SQL direto, propositalmente simples."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
import streamlit as st


def _database_url() -> str:
    # Prioriza st.secrets (padrão Streamlit Cloud), cai pra variável de ambiente.
    # st.secrets lança exceção ao ser acessado se não existir NENHUM secrets.toml,
    # então protegemos com try/except em vez de "in st.secrets" direto.
    try:
        return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Crie .streamlit/secrets.toml "
            "(veja .streamlit/secrets.toml.example) ou defina a variável de "
            "ambiente DATABASE_URL com a connection string do Neon."
        )
    return url


@contextmanager
def get_conn():
    conn = psycopg2.connect(_database_url(), sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(ddl)


# ---------- Usuários ----------

def get_user_by_username(username: str) -> dict[str, Any] | None:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cur.fetchone()


def create_user(username: str, password_hash: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, password_hash),
        )
        return cur.fetchone()[0]


# ---------- Vídeos ----------

def create_video(user_id: int, filename: str, duration_seconds: float | None) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO videos (user_id, filename, duration_seconds, status) "
            "VALUES (%s, %s, %s, 'uploaded') RETURNING id",
            (user_id, filename, duration_seconds),
        )
        return cur.fetchone()[0]


def update_video_status(video_id: int, status: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE videos SET status = %s WHERE id = %s", (status, video_id))


def list_user_videos(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM videos WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
        )
        return cur.fetchall()


# ---------- Transcrição ----------

def save_segments(video_id: int, segments: list[dict[str, Any]]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM transcript_segments WHERE video_id = %s", (video_id,))
        for i, seg in enumerate(segments):
            cur.execute(
                "INSERT INTO transcript_segments (video_id, seq, start_time, end_time, text) "
                "VALUES (%s, %s, %s, %s, %s)",
                (video_id, i, seg["start"], seg["end"], seg["text"]),
            )


def get_segments(video_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM transcript_segments WHERE video_id = %s ORDER BY seq", (video_id,)
        )
        return cur.fetchall()


def update_segment_text(segment_id: int, text: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE transcript_segments SET text = %s, edited = true WHERE id = %s",
            (text, segment_id),
        )


# ---------- Cortes sugeridos ----------

def save_suggested_cuts(video_id: int, cuts: list[dict[str, Any]]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM suggested_cuts WHERE video_id = %s", (video_id,))
        for cut in cuts:
            cur.execute(
                "INSERT INTO suggested_cuts (video_id, title, start_time, end_time, reason, selected) "
                "VALUES (%s, %s, %s, %s, %s, true)",
                (video_id, cut["title"], cut["start"], cut["end"], cut.get("reason", "")),
            )


def get_suggested_cuts(video_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM suggested_cuts WHERE video_id = %s ORDER BY start_time", (video_id,)
        )
        return cur.fetchall()


def set_cut_selected(cut_id: int, selected: bool) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE suggested_cuts SET selected = %s WHERE id = %s", (selected, cut_id))
