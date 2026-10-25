import os, json, base64, hmac, hashlib, time
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.getenv("SECRET_KEY", "local-demo-secret-change-before-deployment-please").encode()
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000).hex()
        return hmac.compare_digest(actual, digest_hex)
    except (ValueError, TypeError):
        return False

def create_access_token(user_id: int) -> str:
    header = _b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub":str(user_id),"exp":int(time.time()) + TOKEN_MINUTES*60}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(SECRET_KEY, signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"

def decode_access_token(token: str):
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(SECRET_KEY, signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < int(time.time()): return None
        return int(data["sub"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
