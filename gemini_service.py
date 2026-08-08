"""Serviço de IA via Gemini: transcrição com timestamps e sugestão de cortes.

Substitui Whisper local (transcrição) + Ollama local (sugestão de corte) por
uma única API na nuvem. Menos infra, sem GPU, mais rápido.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import google.generativeai as genai
import streamlit as st


def _configure() -> None:
    api_key = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    if not api_key:
        import os

        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY não configurada. Crie .streamlit/secrets.toml "
            "(veja .streamlit/secrets.toml.example) ou defina a variável de "
            "ambiente GEMINI_API_KEY."
        )
    genai.configure(api_key=api_key)


def _extract_json(text: str) -> Any:
    """O modelo às vezes envolve o JSON em ```json ... ``` — remove antes de parsear."""
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def _upload_and_wait(video_path: str, on_progress: Callable[[str], None] | None = None):
    _configure()
    if on_progress:
        on_progress("Enviando vídeo para o Gemini...")
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        if on_progress:
            on_progress("Gemini está processando o vídeo...")
        time.sleep(3)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("Falha no processamento do vídeo pelo Gemini.")

    return video_file


def transcribe_video(
    video_path: str, on_progress: Callable[[str], None] | None = None
) -> list[dict[str, Any]]:
    """Retorna lista de segmentos: [{"start": segundos, "end": segundos, "text": str}, ...]"""
    video_file = _upload_and_wait(video_path, on_progress)

    if on_progress:
        on_progress("Transcrevendo áudio...")

    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = (
        "Transcreva o áudio deste vídeo (em português) na íntegra, dividido em segmentos "
        "naturais de fala (frases ou pausas curtas). Responda APENAS com um JSON válido, "
        "sem markdown, no formato:\n"
        '[{"start": 0.0, "end": 4.2, "text": "..."}, ...]\n'
        "Onde start e end são segundos (número, pode ter casas decimais) desde o início do vídeo."
    )
    response = model.generate_content([video_file, prompt])

    try:
        segments = _extract_json(response.text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeError(f"Não consegui interpretar a resposta do Gemini como JSON: {exc}")

    genai.delete_file(video_file.name)  # não deixa lixo na conta do Gemini
    return segments


def suggest_cuts(
    segments: list[dict[str, Any]], on_progress: Callable[[str], None] | None = None
) -> list[dict[str, Any]]:
    """Retorna lista de cortes sugeridos: [{"title", "start", "end", "reason"}, ...]"""
    _configure()
    if on_progress:
        on_progress("Analisando transcrição para sugerir cortes...")

    transcript_text = "\n".join(
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}" for seg in segments
    )

    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = (
        "Você é um editor de vídeo especializado em conteúdo evangélico/cristão para redes "
        "sociais. Analise a transcrição abaixo (com timestamps em segundos) e sugira os "
        "melhores trechos para cortar como clipes curtos (15s a 90s), priorizando momentos "
        "de maior impacto: revelações, aplicações práticas, frases de efeito, chamados à ação.\n\n"
        f"TRANSCRIÇÃO:\n{transcript_text}\n\n"
        "Responda APENAS com um JSON válido, sem markdown, no formato:\n"
        '[{"title": "...", "start": 12.5, "end": 45.0, "reason": "por que esse trecho funciona"}]\n'
        "Sugira entre 2 e 6 cortes. Use os timestamps exatos da transcrição."
    )
    response = model.generate_content(prompt)

    try:
        return _extract_json(response.text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RuntimeError(f"Não consegui interpretar a resposta do Gemini como JSON: {exc}")
