"""Storage de vídeo via Cloudflare R2 (S3-compatible).

O navegador envia o vídeo DIRETO pro R2 via URL pré-assinada — nunca passa
pelo corpo da requisição do Streamlit, então o limite de upload do servidor
(maxUploadSize / RAM) deixa de ser um problema.

Depois, o servidor baixa o objeto do R2 pro disco local (streaming) só na
hora de processar, e apaga tanto do R2 quanto do disco ao final.
"""
from __future__ import annotations

import os

import boto3
import streamlit as st
from botocore.client import Config


def _secret(name: str) -> str:
    try:
        val = st.secrets[name]
        if val:
            return val
    except Exception:
        pass
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"{name} não configurada. Adicione em .streamlit/secrets.toml "
            "(local) ou em Settings > Secrets (Streamlit Cloud)."
        )
    return val


def _client():
    account_id = _secret("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=_secret("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_secret("R2_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _bucket() -> str:
    return _secret("R2_BUCKET_NAME")


def generate_upload_url(object_key: str, expires_in: int = 3600) -> str:
    """URL pré-assinada de PUT — o navegador envia o arquivo direto pra cá."""
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _bucket(), "Key": object_key},
        ExpiresIn=expires_in,
    )


def object_exists(object_key: str) -> bool:
    try:
        _client().head_object(Bucket=_bucket(), Key=object_key)
        return True
    except Exception:
        return False


def download_to_path(object_key: str, local_path: str) -> None:
    """Baixa o objeto do R2 pro disco local, em streaming (não carrega tudo em RAM)."""
    _client().download_file(_bucket(), object_key, local_path)


def delete_object(object_key: str) -> None:
    try:
        _client().delete_object(Bucket=_bucket(), Key=object_key)
    except Exception:
        pass  # descarte é best-effort — não deve quebrar o fluxo do usuário
