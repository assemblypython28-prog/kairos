"""Kairos (simplificado) — login, upload, transcrição por IA, edição e export de cortes.

Arquitetura: Streamlit (front+back) + Neon/Postgres (dados) + Gemini (IA) + ffmpeg (corte).
Sem FastAPI, sem Celery, sem Redis, sem Whisper/Ollama locais.
"""
import os
import shutil
import tempfile
import zipfile

import streamlit as st

import auth
import db
import gemini_service
import video_export

st.set_page_config(page_title="Kairos", page_icon="🎬", layout="wide")


# ---------------------------------------------------------------------------
# Setup / estado de sessão
# ---------------------------------------------------------------------------

def _ensure_schema_once():
    if not st.session_state.get("_schema_ready"):
        db.init_schema()
        st.session_state["_schema_ready"] = True


def _temp_dir() -> str:
    if "temp_dir" not in st.session_state:
        st.session_state["temp_dir"] = tempfile.mkdtemp(prefix="kairos_")
    return st.session_state["temp_dir"]


def _discard_video():
    """Remove o vídeo local do disco. A transcrição/cortes continuam no Neon."""
    temp_dir = st.session_state.get("temp_dir")
    if temp_dir and os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    for key in ("temp_dir", "video_local_path"):
        st.session_state.pop(key, None)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_screen():
    st.title("🎬 Kairos")
    st.caption("Login")

    tab_login, tab_register = st.tabs(["Entrar", "Criar conta"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
        if submitted:
            user = auth.login(username, password)
            if user:
                st.session_state["user"] = {"id": user["id"], "username": user["username"]}
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Novo usuário")
            new_password = st.text_input("Nova senha", type="password")
            submitted_r = st.form_submit_button("Criar conta", use_container_width=True)
        if submitted_r:
            if not new_username or not new_password:
                st.error("Preencha usuário e senha.")
            else:
                try:
                    auth.register(new_username, new_password)
                    st.success("Conta criada! Faça login na aba ao lado.")
                except ValueError as exc:
                    st.error(str(exc))


# ---------------------------------------------------------------------------
# Fluxo principal (usuário logado)
# ---------------------------------------------------------------------------

def upload_step(user):
    st.subheader("1. Envie o vídeo")
    uploaded = st.file_uploader("Vídeo (mp4, mov, mkv)", type=["mp4", "mov", "mkv", "m4v"])

    if uploaded is not None:
        temp_dir = _temp_dir()
        local_path = os.path.join(temp_dir, uploaded.name)
        with open(local_path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.session_state["video_local_path"] = local_path
        st.video(local_path)

        if st.button("Transcrever com IA", type="primary"):
            duration = video_export.get_duration_seconds(local_path)
            video_id = db.create_video(user["id"], uploaded.name, duration)
            st.session_state["video_id"] = video_id
            db.update_video_status(video_id, "transcribing")

            status_box = st.status("Transcrevendo vídeo...", expanded=True)

            def on_progress(msg: str):
                status_box.write(msg)

            try:
                segments = gemini_service.transcribe_video(local_path, on_progress=on_progress)
                db.save_segments(video_id, segments)
                db.update_video_status(video_id, "transcribed")
                status_box.update(label="Transcrição concluída!", state="complete")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                status_box.update(label="Falha na transcrição", state="error")
                st.error(f"Erro: {exc}")


def transcript_step(user, video_id: int):
    st.subheader("2. Transcrição (acompanhe e edite)")

    local_path = st.session_state.get("video_local_path")
    if local_path and os.path.exists(local_path):
        st.video(local_path)

    segments = db.get_segments(video_id)
    if not segments:
        st.info("Nenhuma transcrição encontrada ainda.")
        return

    st.caption("Edite o texto de qualquer trecho e clique em salvar.")
    for seg in segments:
        cols = st.columns([1, 6, 1])
        with cols[0]:
            st.text(f"{seg['start_time']:.1f}s\n–{seg['end_time']:.1f}s")
        with cols[1]:
            new_text = st.text_area(
                f"seg_{seg['id']}", value=seg["text"], key=f"seg_text_{seg['id']}",
                label_visibility="collapsed",
            )
        with cols[2]:
            if st.button("Salvar", key=f"save_{seg['id']}"):
                db.update_segment_text(seg["id"], new_text)
                st.toast("Trecho salvo.")

    st.divider()
    if st.button("Sugerir cortes com IA", type="primary"):
        status_box = st.status("Analisando transcrição...", expanded=True)

        def on_progress(msg: str):
            status_box.write(msg)

        try:
            fresh_segments = db.get_segments(video_id)
            seg_payload = [
                {"start": s["start_time"], "end": s["end_time"], "text": s["text"]}
                for s in fresh_segments
            ]
            cuts = gemini_service.suggest_cuts(seg_payload, on_progress=on_progress)
            db.save_suggested_cuts(video_id, cuts)
            status_box.update(label="Cortes sugeridos!", state="complete")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            status_box.update(label="Falha ao sugerir cortes", state="error")
            st.error(f"Erro: {exc}")


def cuts_step(user, video_id: int):
    cuts = db.get_suggested_cuts(video_id)
    if not cuts:
        return

    st.subheader("3. Cortes sugeridos")
    local_path = st.session_state.get("video_local_path")

    for cut in cuts:
        with st.container(border=True):
            col_check, col_body = st.columns([1, 8])
            with col_check:
                selected = st.checkbox(
                    "", value=cut["selected"], key=f"cutsel_{cut['id']}"
                )
                if selected != cut["selected"]:
                    db.set_cut_selected(cut["id"], selected)
            with col_body:
                st.markdown(f"**{cut['title']}**  ·  {cut['start_time']:.1f}s – {cut['end_time']:.1f}s")
                if cut.get("reason"):
                    st.caption(cut["reason"])

    selected_cuts = [c for c in cuts if c["selected"]]
    st.divider()
    if st.button(f"Exportar {len(selected_cuts)} clipe(s) selecionado(s)", type="primary",
                 disabled=not (selected_cuts and local_path and os.path.exists(local_path))):
        export_dir = os.path.join(_temp_dir(), "export")
        os.makedirs(export_dir, exist_ok=True)
        clip_paths = []
        progress = st.progress(0.0, text="Cortando clipes...")
        for i, cut in enumerate(selected_cuts):
            safe_title = "".join(c for c in cut["title"] if c.isalnum() or c in " -_").strip()[:40]
            out_path = os.path.join(export_dir, f"{i+1:02d}_{safe_title or 'clipe'}.mp4")
            video_export.cut_clip(local_path, float(cut["start_time"]), float(cut["end_time"]), out_path)
            clip_paths.append(out_path)
            progress.progress((i + 1) / len(selected_cuts), text=f"Clipe {i+1}/{len(selected_cuts)} pronto")

        if len(clip_paths) == 1:
            with open(clip_paths[0], "rb") as f:
                st.download_button(
                    "Baixar clipe", f.read(), file_name=os.path.basename(clip_paths[0]),
                    mime="video/mp4",
                )
        else:
            zip_path = os.path.join(export_dir, "clipes_kairos.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                for p in clip_paths:
                    zf.write(p, arcname=os.path.basename(p))
            with open(zip_path, "rb") as f:
                st.download_button(
                    "Baixar todos (.zip)", f.read(), file_name="clipes_kairos.zip",
                    mime="application/zip",
                )

    if local_path and os.path.exists(local_path):
        st.divider()
        if st.button("Descartar vídeo do servidor (a transcrição continua salva)"):
            _discard_video()
            st.success("Vídeo descartado do disco. Dados de transcrição/cortes seguem no Neon.")
            st.rerun()


def main_app(user):
    st.sidebar.write(f"Logado como **{user['username']}**")
    if st.sidebar.button("Sair"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption("Seus vídeos")
    for v in db.list_user_videos(user["id"]):
        label = f"{v['filename']} ({v['status']})"
        if st.sidebar.button(label, key=f"vid_{v['id']}", use_container_width=True):
            st.session_state["video_id"] = v["id"]
            st.session_state.pop("video_local_path", None)
            st.rerun()
    if st.sidebar.button("➕ Novo vídeo", use_container_width=True):
        _discard_video()
        st.session_state.pop("video_id", None)
        st.rerun()

    st.title("🎬 Kairos")

    video_id = st.session_state.get("video_id")
    if not video_id:
        upload_step(user)
        return

    transcript_step(user, video_id)
    cuts_step(user, video_id)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

_ensure_schema_once()

if "user" not in st.session_state:
    login_screen()
else:
    main_app(st.session_state["user"])
