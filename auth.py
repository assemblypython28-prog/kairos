"""Autenticação simples: usuário/senha com bcrypt. Sem OAuth, sem JWT — direto ao ponto."""
import bcrypt

import db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def login(username: str, password: str) -> dict | None:
    user = db.get_user_by_username(username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def register(username: str, password: str) -> dict:
    if db.get_user_by_username(username):
        raise ValueError("Usuário já existe.")
    user_id = db.create_user(username, hash_password(password))
    return {"id": user_id, "username": username}
