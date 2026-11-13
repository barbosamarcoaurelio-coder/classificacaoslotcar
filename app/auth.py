import hashlib
import os
import hmac
import time
import json
import base64

SECRET_KEY = os.environ.get("APP_SECRET_KEY", "gt-racing-slot-car-secret-key-2026")

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return salt.hex() + ":" + pwd_hash.hex()

def verify_password(stored: str, password: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(expected_hash.hex(), hash_hex)
    except Exception:
        return False

def create_session_token(email: str, is_admin: bool = True) -> str:
    payload = {
        "email": email,
        "is_admin": is_admin,
        "exp": int(time.time()) + (86400 * 30) # 30 dias
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    b64_data = base64.urlsafe_b64encode(data_bytes).decode("utf-8").rstrip("=")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_data}.{sig}"

def verify_session_token(token: str) -> dict:
    if not token or "." not in token:
        return None
    try:
        b64_data, sig = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_data.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, sig):
            return None
        # padding
        padding = "=" * (4 - (len(b64_data) % 4)) if len(b64_data) % 4 != 0 else ""
        raw = base64.urlsafe_b64decode(b64_data + padding).decode("utf-8")
        payload = json.loads(raw)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
