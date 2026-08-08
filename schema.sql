-- Kairos (versão simplificada) — schema Neon/Postgres
-- Guarda só dados estruturados. O arquivo de vídeo NUNCA é persistido aqui,
-- fica em disco local temporário durante o processamento e é descartado depois.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS videos (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    duration_seconds NUMERIC,
    status TEXT NOT NULL DEFAULT 'uploaded', -- uploaded | transcribing | transcribed | cutting | done
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    start_time NUMERIC NOT NULL,  -- segundos
    end_time NUMERIC NOT NULL,    -- segundos
    text TEXT NOT NULL,
    edited BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS suggested_cuts (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_time NUMERIC NOT NULL,
    end_time NUMERIC NOT NULL,
    reason TEXT,
    selected BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_segments_video ON transcript_segments(video_id);
CREATE INDEX IF NOT EXISTS idx_cuts_video ON suggested_cuts(video_id);
