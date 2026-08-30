"""
KYRO ANIME - Military-Grade Security Hardened Backend
Version: V1.0-SECURE-RENDER
Author: neokyro (Lawrence)
Platform: Render.com (PaaS)
Security Level: Defense-in-Depth
Note: Adapted for Render deployment. TLS, rate limiting, and WAF handled by Render + app layer.
"""

from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context, g, abort
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import requests
import os, re, subprocess, traceback, hashlib, secrets, string, hmac, time, ipaddress
from functools import wraps
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from user_agents import parse as ua_parse
import json

# ===== SECURITY CONFIG =====
class SecurityConfig:
    PASSWORD_MIN_LENGTH = 12
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_SECONDS = 3600
    SESSION_TIMEOUT_MINUTES = 15
    RATE_LIMIT_GLOBAL = "200 per minute"
    RATE_LIMIT_AUTH = "5 per minute"
    RATE_LIMIT_ADMIN = "30 per minute"
    RATE_LIMIT_DOWNLOAD = "3 per minute"

    CSP = {
        "default-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data: https:",
        "connect-src": "'self'",
        "font-src": "'self'",
        "frame-ancestors": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "upgrade-insecure-requests": "",
    }

    ALLOWED_ORIGINS = os.environ.get("KYRO_ALLOWED_ORIGINS", "https://yourdomain.com").split(",")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    AI_ERROR_KEY = os.environ.get("AI_ERROR_KEY", "")
    OWNER_KEY = os.environ.get("KYRO_OWNER_KEY", "")
    STAFF_KEY = os.environ.get("KYRO_STAFF_KEY", "")
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(64))
    ADMIN_TRIGGER = os.environ.get("KYRO_ADMIN_TRIGGER", "rkpg9xh2f3adminkyrolawrenceinfinitycodexneokyro")

# ===== ARGON2ID =====
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=2)
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    print("[SECURITY WARNING] argon2-cffi not installed. Falling back to PBKDF2.")

def hash_password(password):
    if ARGON2_AVAILABLE:
        return ph.hash(password)
    salt = secrets.token_hex(32)
    hash_val = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    return f"pbkdf2_sha256$600000${salt}${hash_val.hex()}"

def verify_password(password, hash_str):
    if ARGON2_AVAILABLE:
        try:
            ph.verify(hash_str, password)
            return True
        except:
            return False
    if not hash_str.startswith("pbkdf2_sha256$"):
        return False
    parts = hash_str.split("$")
    if len(parts) != 4:
        return False
    _, _, salt, stored_hash = parts
    computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    return hmac.compare_digest(computed.hex(), stored_hash)

# ===== HMAC =====
def sign_data(data, secret=None):
    secret = secret or SecurityConfig.SECRET_KEY
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()

def verify_signature(data, signature, secret=None):
    return hmac.compare_digest(sign_data(data, secret), signature)

# ===== UTILS =====
def generate_secure_token(length=64):
    return secrets.token_urlsafe(length)

def generate_unlock_code():
    return "".join(secrets.choice(string.digits) for _ in range(6))

def generate_nonce():
    return secrets.token_hex(16)

def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            pass
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        try:
            ipaddress.ip_address(real_ip)
            return real_ip
        except ValueError:
            pass
    return request.remote_addr or "unknown"

def is_private_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False

HTML_ESCAPE_MAP = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;", "/": "&#x2F;"}

def sanitize_html(text):
    if not text:
        return ""
    return "".join(HTML_ESCAPE_MAP.get(c, c) for c in str(text))

def sanitize_filename(filename):
    if not filename:
        return "file"
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9._-]", "", filename)
    if not filename or filename.startswith("."):
        filename = "file" + filename
    return filename[:255]

def validate_url(url, allowed_schemes=None):
    if not url or len(url) > 2048:
        return False
    allowed = allowed_schemes or ["http", "https"]
    parsed = requests.utils.urlparse(url)
    if parsed.scheme not in allowed:
        return False
    try:
        host = parsed.hostname
        if host:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback:
                return False
    except ValueError:
        pass
    return True

# ===== AUTH MANAGER =====
DEFAULT_PASSWORD_HASH = hash_password(os.environ.get("KYRO_PASSWORD", "kyro2026"))
MAX_ATTEMPTS = SecurityConfig.MAX_LOGIN_ATTEMPTS
LOCKOUT_DURATION = SecurityConfig.LOCKOUT_DURATION_SECONDS

class AuthManager:
    def __init__(self):
        self.failed_attempts = {}
        self.unlock_codes = []
        self.current_password_hash = DEFAULT_PASSWORD_HASH
        self.sessions = {}

    def is_locked_out(self, ip):
        if ip not in self.failed_attempts:
            return False
        record = self.failed_attempts[ip]
        if record.get("locked_until"):
            if datetime.now() < record["locked_until"]:
                return True
            self.failed_attempts[ip] = {"count": 0, "last_attempt": None, "locked_until": None}
            return False
        return False

    def record_failed_attempt(self, ip):
        if ip not in self.failed_attempts:
            self.failed_attempts[ip] = {"count": 0, "last_attempt": None, "locked_until": None}
        self.failed_attempts[ip]["count"] += 1
        self.failed_attempts[ip]["last_attempt"] = datetime.now()
        if self.failed_attempts[ip]["count"] >= MAX_ATTEMPTS:
            self.failed_attempts[ip]["locked_until"] = datetime.now() + timedelta(seconds=LOCKOUT_DURATION)

    def reset_attempts(self, ip):
        if ip in self.failed_attempts:
            del self.failed_attempts[ip]

    def get_remaining_attempts(self, ip):
        if ip not in self.failed_attempts:
            return MAX_ATTEMPTS
        return max(0, MAX_ATTEMPTS - self.failed_attempts[ip]["count"])

    def check_password(self, password):
        return verify_password(password, self.current_password_hash)

    def set_password(self, password):
        if len(password) < SecurityConfig.PASSWORD_MIN_LENGTH:
            raise ValueError("Password must be at least %d characters" % SecurityConfig.PASSWORD_MIN_LENGTH)
        self.current_password_hash = hash_password(password)

    def create_session(self, ip, user_agent, role="user"):
        token = generate_secure_token(48)
        expires = datetime.now() + timedelta(minutes=SecurityConfig.SESSION_TIMEOUT_MINUTES)
        self.sessions[token] = {"ip": ip, "user_agent": user_agent[:200], "role": role, "expires": expires, "created": datetime.now().isoformat()}
        return token

    def validate_session(self, token, ip, user_agent):
        if not token or token not in self.sessions:
            return None
        session = self.sessions[token]
        if datetime.now() > session["expires"]:
            del self.sessions[token]
            return None
        if session.get("ip") != ip:
            log_security_event("SESSION_IP_MISMATCH", "Token used from different IP: %s vs %s" % (ip, session.get("ip")), ip)
        return session

    def revoke_session(self, token):
        if token in self.sessions:
            del self.sessions[token]

    def cleanup_expired_sessions(self):
        now = datetime.now()
        expired = [t for t, s in self.sessions.items() if now > s["expires"]]
        for t in expired:
            del self.sessions[t]

auth_manager = AuthManager()

# ===== SECURITY LOG =====
SECURITY_LOG = "/tmp/kyro_security.json"

def log_security_event(event_type, details, ip=None, severity="info"):
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": str(details)[:500],
            "ip": ip or get_client_ip(),
            "severity": severity,
            "user_agent": request.headers.get("User-Agent", "")[:200] if request else "",
            "path": request.path if request else "",
            "method": request.method if request else ""
        }
        entry["integrity"] = sign_data(json.dumps(entry, sort_keys=True, default=str))
        logs = []
        if os.path.exists(SECURITY_LOG):
            try:
                with open(SECURITY_LOG, "r") as f:
                    logs = json.load(f)
            except:
                pass
        logs.append(entry)
        logs = logs[-1000:]
        with open(SECURITY_LOG, "w") as f:
            json.dump(logs, f, indent=2)
        print("[SECURITY %s] %s: %s" % (severity.upper(), event_type, str(details)[:100]))
    except Exception as e:
        print("[SECURITY LOGGING FAILED] %s" % e)

# ===== ERROR LOGGING =====
ERROR_LOG = "/tmp/kyro_errors.json"
AI_ERROR_QUEUE = []
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.1-70b-versatile")

def log_error(error_type, error_msg, traceback_str, endpoint="", user_agent=""):
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": str(error_msg)[:500],
            "traceback": traceback_str[:2000],
            "endpoint": endpoint,
            "user_agent": user_agent[:200],
            "analyzed": False,
            "ai_diagnosis": "",
            "ai_fix": ""
        }
        errors = []
        if os.path.exists(ERROR_LOG):
            try:
                with open(ERROR_LOG, "r") as f:
                    errors = json.load(f)
            except:
                pass
        errors.append(entry)
        errors = errors[-200:]
        with open(ERROR_LOG, "w") as f:
            json.dump(errors, f, indent=2)
        AI_ERROR_QUEUE.append(entry)
        if len(AI_ERROR_QUEUE) > 50:
            AI_ERROR_QUEUE.pop(0)
        print("[KYRO ERROR] %s: %s" % (error_type, str(error_msg)[:100]))
    except Exception as e:
        print("[KYRO ERROR LOGGING FAILED] %s" % e)

def analyze_error_with_ai(error_entry):
    if not SecurityConfig.AI_ERROR_KEY:
        return {"diagnosis": "No AI key configured.", "fix": "N/A"}
    prompt = "You are a Python/Flask debugging expert. Analyze this error and provide:\n1. A clear diagnosis\n2. A specific code fix\n\nError Type: %s\nError Message: %s\nEndpoint: %s\nTraceback:\n%s\n\nRespond in this exact format:\nDIAGNOSIS: [diagnosis]\nFIX: [fix]" % (
        error_entry["type"], error_entry["message"], error_entry["endpoint"], error_entry["traceback"]
    )
    try:
        payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1024}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer %s" % SecurityConfig.AI_ERROR_KEY, "Content-Type": "application/json"},
            json=payload, timeout=30)
        result = r.json()
        if "choices" in result:
            text = result["choices"][0]["message"]["content"]
            diagnosis = ""
            fix = ""
            if "DIAGNOSIS:" in text:
                parts = text.split("FIX:")
                diagnosis = parts[0].replace("DIAGNOSIS:", "").strip()
                fix = parts[1].strip() if len(parts) > 1 else "See full response"
            else:
                diagnosis = text[:200]
                fix = text[200:500] if len(text) > 200 else "N/A"
            return {"diagnosis": diagnosis, "fix": fix, "full_response": text}
    except Exception as e:
        return {"diagnosis": "AI analysis failed: %s" % str(e), "fix": "N/A"}
    return {"diagnosis": "Could not analyze", "fix": "N/A"}

# ===== VISITOR TRACKING =====
VISITOR_LOG = "/tmp/kyro_visitors.json"

def log_visitor(request, action="page_view", details=""):
    try:
        ua_string = request.headers.get("User-Agent", "")
        ua = ua_parse(ua_string)
        ip = get_client_ip()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "ip": sanitize_html(ip.split(",")[0].strip() if "," in ip else ip),
            "device": sanitize_html(ua.device.family or "Unknown"),
            "brand": sanitize_html(ua.device.brand or "Unknown"),
            "model": sanitize_html(ua.device.model or "Unknown"),
            "os": sanitize_html("%s %s" % (ua.os.family, ua.os.version_string) if ua.os.version_string else ua.os.family),
            "browser": sanitize_html("%s %s" % (ua.browser.family, ua.browser.version_string) if ua.browser.version_string else ua.browser.family),
            "is_mobile": ua.is_mobile,
            "is_tablet": ua.is_tablet,
            "is_pc": ua.is_pc,
            "action": sanitize_html(action),
            "details": sanitize_html(str(details)[:200]),
            "path": sanitize_html(request.path)
        }
        logs = []
        if os.path.exists(VISITOR_LOG):
            try:
                with open(VISITOR_LOG, "r") as f:
                    logs = json.load(f)
            except:
                pass
        logs.append(entry)
        logs = logs[-5000:]
        with open(VISITOR_LOG, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print("[KYRO LOG ERROR] %s" % e)

# ===== ROLE-BASED KEYS =====
def get_role_from_key(key):
    if not key or len(key) < 32:
        return None
    if SecurityConfig.OWNER_KEY and hmac.compare_digest(key, SecurityConfig.OWNER_KEY):
        return "owner"
    if SecurityConfig.STAFF_KEY and hmac.compare_digest(key, SecurityConfig.STAFF_KEY):
        return "staff"
    return None

def require_role(min_role="staff"):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            key = request.headers.get("X-Admin-Key", "")
            role = get_role_from_key(key)
            if not role:
                log_security_event("UNAUTHORIZED_ADMIN_ACCESS", "Invalid key attempt on %s" % request.path, severity="warning")
                return jsonify({"error": "Invalid or missing admin key"}), 403
            if min_role == "owner" and role != "owner":
                log_security_event("PRIVILEGE_ESCALATION_ATTEMPT", "Staff tried owner action: %s" % request.path, severity="warning")
                return jsonify({"error": "Owner access required"}), 403
            g.user_role = role
            g.session_token = request.headers.get("X-Session-Token", "")
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ===== FFMPEG =====
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        FFMPEG_AVAILABLE = True
except:
    pass

# ===== FLASK APP =====
app = Flask(__name__)
app.secret_key = SecurityConfig.SECRET_KEY
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=SecurityConfig.SESSION_TIMEOUT_MINUTES)

limiter = Limiter(
    app=app,
    key_func=get_client_ip,
    default_limits=[SecurityConfig.RATE_LIMIT_GLOBAL],
    storage_uri="memory://"
)

Talisman(app,
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=63072000,
    strict_transport_security_include_subdomains=True,
    content_security_policy=SecurityConfig.CSP,
    referrer_policy="strict-origin-when-cross-origin",
    feature_policy={"geolocation": "'none'", "microphone": "'none'", "camera": "'none'", "payment": "'none'"}
)

CORS(app, resources={
    r"/api/*": {"origins": SecurityConfig.ALLOWED_ORIGINS},
    r"/admin/*": {"origins": SecurityConfig.ALLOWED_ORIGINS}
}, supports_credentials=True)

# ===== SECURITY MIDDLEWARE =====
@app.before_request
def security_before_request():
    g.start_time = datetime.now()
    g.nonce = generate_nonce()

    if request.path.startswith("/admin/"):
        log_security_event("ADMIN_ACCESS", "%s %s" % (request.method, request.path), severity="info")

    blocked_patterns = [
        r"\.\./", r"<script", r"javascript:", r"union\s+select",
        r"drop\s+table", r"';\s*--", r"\b(etc/passwd|win\.ini|boot\.ini)\b",
    ]
    query = request.query_string.decode("utf-8", errors="ignore")
    body = request.get_data(as_text=True)[:2000]
    for pattern in blocked_patterns:
        if re.search(pattern, query, re.IGNORECASE) or re.search(pattern, body, re.IGNORECASE):
            log_security_event("WAF_BLOCK", "Blocked pattern: %s on %s" % (pattern, request.path), severity="high")
            abort(403, description="Request blocked by security policy")

    if SERVER_STOPPED and not request.path.startswith("/admin/"):
        return jsonify({"error": "Server is under maintenance", "maintenance": True}), 503

@app.after_request
def security_after_request(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers.pop("Server", None)
    response.headers.pop("X-Powered-By", None)

    if hasattr(g, "start_time"):
        duration = (datetime.now() - g.start_time).total_seconds()
        response.headers["X-Response-Time"] = "%.3fs" % duration
        if duration > 5:
            log_error("SLOW_REQUEST", "Request took %.1fs" % duration,
                      "Endpoint: %s\nMethod: %s" % (request.path, request.method), endpoint=request.path)
        if response.status_code >= 500:
            log_error("HTTP_500", "Status %d" % response.status_code,
                      "Endpoint: %s" % request.path, endpoint=request.path)
    return response

@app.errorhandler(403)
def handle_403(error):
    log_security_event("FORBIDDEN", str(error.description) if hasattr(error, "description") else str(error), severity="warning")
    return jsonify({"error": "Forbidden", "code": 403}), 403

@app.errorhandler(404)
def handle_404(error):
    return jsonify({"error": "Not found", "code": 404}), 404

@app.errorhandler(429)
def handle_429(error):
    log_security_event("RATE_LIMIT_EXCEEDED", "%s - %s" % (request.path, error.description), severity="warning")
    return jsonify({"error": "Rate limit exceeded. Please slow down.", "code": 429}), 429

@app.errorhandler(Exception)
def handle_error(error):
    tb = traceback.format_exc()
    log_error(type(error).__name__, str(error), tb, endpoint=request.path, user_agent=request.headers.get("User-Agent", ""))
    return jsonify({"error": "Internal server error", "type": type(error).__name__, "trace_id": sign_data(str(datetime.now()))[:16]}), 500

# ===== CONSTANTS =====
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ANILIST_URL = "https://graphql.anilist.co"
ANIMEHEAVEN = "https://animeheaven.me"
SYSTEM_PROMPT = "You are KYRO, an AI anime expert."

_AH_STATUS_CACHE = {"status": False, "time": 0}

def get_ah_status():
    global _AH_STATUS_CACHE
    now = datetime.now().timestamp()
    if now - _AH_STATUS_CACHE["time"] > 60:
        try:
            _AH_STATUS_CACHE["status"] = requests.get(ANIMEHEAVEN, timeout=5).status_code == 200
        except:
            _AH_STATUS_CACHE["status"] = False
        _AH_STATUS_CACHE["time"] = now
    return _AH_STATUS_CACHE["status"]

# ===== PASSWORD API ENDPOINTS =====

@app.route("/api/password/check", methods=["POST"])
@limiter.limit(SecurityConfig.RATE_LIMIT_AUTH)
def password_check():
    data = request.get_json() or {}
    pwd = data.get("password", "")
    ip = get_client_ip()

    if auth_manager.is_locked_out(ip):
        log_security_event("LOCKED_OUT_LOGIN_ATTEMPT", "IP %s tried to login while locked out" % ip, severity="warning")
        return jsonify({"locked": True, "message": "Too many failed attempts. Contact admin for unlock code."}), 403

    if auth_manager.check_password(pwd):
        auth_manager.reset_attempts(ip)
        token = auth_manager.create_session(ip, request.headers.get("User-Agent", ""))
        log_security_event("SUCCESSFUL_LOGIN", "IP %s authenticated successfully" % ip, severity="info")
        return jsonify({"success": True, "role": "user", "session_token": token})
    else:
        auth_manager.record_failed_attempt(ip)
        remaining = auth_manager.get_remaining_attempts(ip)
        log_security_event("FAILED_LOGIN", "IP %s failed login. Remaining: %d" % (ip, remaining), severity="warning")
        return jsonify({"success": False, "remaining": remaining, "locked": remaining == 0})

@app.route("/api/password/remaining")
def password_remaining():
    ip = get_client_ip()
    return jsonify({"remaining": auth_manager.get_remaining_attempts(ip), "locked": auth_manager.is_locked_out(ip)})

@app.route("/api/password/unlock-request", methods=["POST"])
@limiter.limit("3 per hour")
def password_unlock_request():
    data = request.get_json() or {}
    ip = get_client_ip()
    device = sanitize_html(data.get("device", "Unknown"))
    code = generate_unlock_code()
    entry = {"timestamp": datetime.now().isoformat(), "code": code, "ip": ip, "device": device, "used": False}
    auth_manager.unlock_codes.append(entry)
    if len(auth_manager.unlock_codes) > 100:
        auth_manager.unlock_codes.pop(0)
    log_security_event("UNLOCK_REQUEST", "IP %s requested unlock" % ip, severity="info")
    return jsonify({"success": True, "message": "Unlock request sent to admin. Wait for admin to unlock you."})

@app.route("/admin/api/unlock-codes")
@require_role("owner")
def admin_unlock_codes():
    pending = [u for u in auth_manager.unlock_codes if not u.get("used")]
    return jsonify({"codes": pending, "total_pending": len(pending)})

@app.route("/admin/api/unlock", methods=["POST"])
@require_role("owner")
def admin_unlock():
    data = request.get_json() or {}
    code = sanitize_html(data.get("code", "").strip())
    new_password = data.get("new_password", "").strip()
    found = False
    for u in auth_manager.unlock_codes:
        if u.get("code") == code and not u.get("used"):
            u["used"] = True
            found = True
            auth_manager.reset_attempts(u.get("ip", ""))
            break
    if not found:
        log_security_event("INVALID_UNLOCK_ATTEMPT", "Code: %s" % code, severity="warning")
        return jsonify({"error": "Invalid or used unlock code"}), 400
    if new_password and len(new_password) >= SecurityConfig.PASSWORD_MIN_LENGTH:
        try:
            auth_manager.set_password(new_password)
            log_security_event("PASSWORD_CHANGED", "Password changed via admin unlock", severity="info")
            return jsonify({"success": True, "message": "User unlocked and password changed."})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    log_security_event("USER_UNLOCKED", "IP unlocked via code", severity="info")
    return jsonify({"success": True, "message": "User unlocked. Password unchanged."})

@app.route("/admin/api/change-password", methods=["POST"])
@require_role("owner")
def admin_change_password():
    data = request.get_json() or {}
    new_password = data.get("new_password", "").strip()
    try:
        auth_manager.set_password(new_password)
        log_security_event("PASSWORD_CHANGED", "Password changed by admin", severity="info")
        return jsonify({"success": True, "message": "Password updated successfully."})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# ===== ANILIST FUNCTIONS =====
def anilist_search(query, limit=20):
    q = "query ($search: String, $perPage: Int) { Page(page: 1, perPage: $perPage) { media(search: $search, type: ANIME) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status } } }"
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"search": query, "perPage": limit}}, timeout=15)
    data = r.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])
    results = []
    for m in media:
        results.append({"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:300], "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"]})
    return results

def anilist_trending(limit=20):
    q = "query ($perPage: Int) { Page(page: 1, perPage: $perPage) { media(type: ANIME, sort: TRENDING_DESC) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status } } }"
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"perPage": limit}}, timeout=15)
    data = r.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])
    results = []
    for m in media:
        results.append({"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:300], "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"]})
    return results

def anilist_detail(anime_id):
    q = "query ($id: Int) { Media(id: $id, type: ANIME) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status trailer { id site } } }"
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"id": anime_id}}, timeout=15)
    data = r.json()
    m = data.get("data", {}).get("Media", {})
    return {"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", ""), "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"], "trailer": m.get("trailer", {}).get("id", "")}

def anilist_seasonal(limit=20):
    import datetime
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    if month in [1,2,3]: season = "WINTER"
    elif month in [4,5,6]: season = "SPRING"
    elif month in [7,8,9]: season = "SUMMER"
    else: season = "FALL"
    q = "query ($season: MediaSeason, $seasonYear: Int, $perPage: Int) { Page(page: 1, perPage: $perPage) { media(type: ANIME, season: $season, seasonYear: $seasonYear, sort: POPULARITY_DESC) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status } } }"
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"season": season, "seasonYear": year, "perPage": limit}}, timeout=15)
    data = r.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])
    results = []
    for m in media:
        results.append({"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:300], "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"]})
    return results

# ===== ANIMEHEAVEN FUNCTIONS =====
def ah_get_episodes(anime_id):
    try:
        r = requests.get("%s/anime.php?%s" % (ANIMEHEAVEN, anime_id), headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": ANIMEHEAVEN}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        title, image, desc = "", "", ""
        h1 = soup.find("h1")
        if h1: title = h1.get_text(strip=True)
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "image.php" in src: image = src if src.startswith("http") else "%s/%s" % (ANIMEHEAVEN, src); break
        info = soup.find("div", class_="infodes")
        if info: desc = info.get_text(strip=True)
        episodes = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            onclick = a.get("onclick", "")
            if "gate.php" in href and "gatea" in onclick:
                match = re.search(r'gatea\("([^"]+)"\)', onclick)
                if match:
                    ep_hash = match.group(1)
                    watch2 = a.find("div", class_=lambda x: x and "watch2" in str(x))
                    if watch2:
                        ep_num = watch2.get_text(strip=True)
                    else:
                        ep_num = "0"
                    episodes.append({"hash": ep_hash, "number": ep_num, "title": "Episode %s" % ep_num, "anime_id": anime_id})
        return {"title": title, "image": image, "description": desc, "episodes": episodes}
    except Exception as e:
        return {"error": str(e), "episodes": []}

def ah_get_stream_url(ep_hash):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "%s/anime.php" % ANIMEHEAVEN})
        session.cookies.set("key", ep_hash, domain="animeheaven.me")
        r = session.get("%s/gate.php" % ANIMEHEAVEN, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        sources = soup.find_all("source")
        for src in sources:
            url = src.get("src", "")
            if url and ".mp4" in url and "error" not in url: return url
        video = soup.find("video")
        if video:
            url = video.get("src", "")
            if url: return url
        return None
    except: return None

def ah_search_anime(query):
    try:
        r = requests.get("%s/search.php" % ANIMEHEAVEN, params={"s": query}, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": ANIMEHEAVEN}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "anime.php" in href:
                anime_id = href.split("?")[-1]
                title = a.get_text(strip=True)
                if title and anime_id: results.append({"id": anime_id, "title": title, "url": "%s/%s" % (ANIMEHEAVEN, href)})
        return results
    except: return []

# ===== MAIN ROUTES =====
@app.route("/")
def index():
    log_visitor(request, "page_view", "Loaded homepage")
    try:
        with open("templates/index.html", "r") as f:
            html = f.read()
        return render_template_string(html)
    except:
        with open("index.html", "r") as f:
            html = f.read()
        return render_template_string(html)

@app.route("/api/status")
def status():
    try: ah_ok = requests.get(ANIMEHEAVEN, timeout=10).status_code == 200
    except: ah_ok = False
    try: anilist_ok = requests.post(ANILIST_URL, json={"query": "{Page(page:1,perPage:1){media(type:ANIME){id}}}", "variables": {}}, timeout=10).status_code == 200
    except: anilist_ok = False
    return jsonify({
        "animeheaven": "connected" if ah_ok else "disconnected",
        "anilist": "connected" if anilist_ok else "disconnected",
        "groq": "connected" if SecurityConfig.GROQ_API_KEY else "no_key",
        "ffmpeg": "available" if FFMPEG_AVAILABLE else "not_installed"
    })

@app.route("/api/chat", methods=["POST"])
@limiter.limit("30 per minute")
def chat():
    data = request.get_json()
    msg = data.get("messages", [{}])[-1].get("content", "") if data.get("messages") else ""
    log_visitor(request, "chat", "Chat message: %s..." % msg[:50])
    messages = data.get("messages", [])
    using_default_key = not SecurityConfig.GROQ_API_KEY or len(SecurityConfig.GROQ_API_KEY) < 20
    has_real_key = SecurityConfig.GROQ_API_KEY and not using_default_key
    if has_real_key:
        payload = {"model": AI_MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages, "temperature": 0.8, "max_tokens": 1024}
        try:
            r = requests.post(GROQ_URL, headers={"Authorization": "Bearer %s" % SecurityConfig.GROQ_API_KEY, "Content-Type": "application/json"}, json=payload, timeout=30)
            result = r.json()
            if "choices" in result and len(result["choices"]) > 0:
                return jsonify({"reply": result["choices"][0]["message"]["content"]})
            elif "error" in result:
                error_msg = result["error"].get("message", "Unknown Groq error")
                if "invalid" in error_msg.lower() or "auth" in error_msg.lower() or "key" in error_msg.lower():
                    return jsonify({"reply": "[API KEY INVALID] %s. Set a valid GROQ_API_KEY env var. Using fallback mode." % error_msg, "fallback": True})
                return jsonify({"reply": "[Groq Error] %s. Using fallback mode." % error_msg, "fallback": True})
        except requests.exceptions.Timeout:
            return jsonify({"reply": "[Groq Timeout] AI service is slow. Using fallback mode.", "fallback": True})
        except requests.exceptions.ConnectionError:
            return jsonify({"reply": "[Groq Offline] Cannot connect to AI service. Check your internet. Using fallback mode.", "fallback": True})
        except Exception as e:
            return jsonify({"reply": "[Groq Error] %s. Using fallback mode." % str(e), "fallback": True})
    fallback_reply = generate_ai_response(msg, messages)
    if using_default_key:
        fallback_reply += "\n\n---\nTo enable full AI chat, set your Groq API key:\nexport GROQ_API_KEY=your-key-here\nGet one free at groq.com"
    return jsonify({"reply": fallback_reply, "fallback": True})

def generate_ai_response(msg, messages):
    msg_lower = msg.lower()
    if any(w in msg_lower for w in ["hello", "hi", "hey", "sup"]):
        return "Hey there! I am KYRO, your anime assistant. Looking for recommendations or info on a specific show?"
    if any(w in msg_lower for w in ["recommend", "suggest", "what should", "good anime", "best anime"]):
        return "Here are some top picks across genres:\n\n**Action:** Demon Slayer, Jujutsu Kaisen, Attack on Titan\n**Romance:** Your Name, Toradora, Horimiya\n**Isekai:** Re:Zero, Mushoku Tensei, Saga of Tanya\n**Thriller:** Death Note, Steins;Gate, Monster\n\nWant something more specific? Tell me your favorite genre!"
    genres = {
        "action": "Try Demon Slayer, Jujutsu Kaisen, Chainsaw Man, or Vinland Saga!",
        "romance": "Check out Your Name, Toradora, Clannad, or Kaguya-sama: Love is War!",
        "comedy": "Nichijou, Gintama, KonoSuba, and The Disastrous Life of Saiki K are hilarious!",
        "horror": "Try Another, Higurashi, Tokyo Ghoul, or Parasyte!",
        "isekai": "Re:Zero, Mushoku Tensei, Overlord, and That Time I Got Reincarnated as a Slime are top tier!",
        "sports": "Haikyuu!!, Kuroko's Basketball, Blue Lock, and Hajime no Ippo!",
        "mecha": "Code Geass, Evangelion, Gurren Lagann, and 86!",
        "slice of life": "Barakamon, Non Non Biyori, Laid-Back Camp, and Yuru Camp!",
        "fantasy": "Made in Abyss, Frieren, Fullmetal Alchemist: Brotherhood!",
    }
    for genre, response in genres.items():
        if genre in msg_lower:
            return response
    if any(w in msg_lower for w in ["episode", "watch", "stream", "download"]):
        return "You can browse anime on the home page, click any card to see episodes, then hit Play or Download. I can also help you find specific shows - just tell me the name!"
    if any(w in msg_lower for w in ["search", "find", "where"]):
        return "Click the search icon (magnifying glass) in the top nav or bottom bar. Type any anime title, genre, or keyword and I will find matches for you!"
    if any(w in msg_lower for w in ["help", "how to", "what can"]):
        return "I can help you with:\n- Anime recommendations by genre\n- Finding where to watch specific shows\n- Info about episodes and seasons\n- General anime discussions\n\nJust ask me anything!"
    return "That is interesting! As an anime expert, I would love to help more. Are you looking for recommendations, info about a specific show, or help using KYRO? Just let me know what you are into!"

@app.route("/api/seasonal")
def seasonal():
    try:
        return jsonify({"results": anilist_seasonal(20)})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

@app.route("/api/search")
def search():
    q = sanitize_html(request.args.get("q", ""))
    if q:
        log_visitor(request, "search", "Searched for: %s" % q)
    if not q: return jsonify({"results": anilist_trending(20)})
    try: return jsonify({"results": anilist_search(q, 20)})
    except Exception as e: return jsonify({"results": [], "error": str(e)})

@app.route("/api/anime/<int:anime_id>")
def anime_detail(anime_id):
    log_visitor(request, "view_anime", "Viewed anime ID: %d" % anime_id)
    try: return jsonify(anilist_detail(anime_id))
    except Exception as e: return jsonify({"error": str(e)})

@app.route("/api/animeheaven/search")
def ah_search_route():
    q = sanitize_html(request.args.get("q", ""))
    if not q: return jsonify({"results": []})
    return jsonify({"results": ah_search_anime(q)})

@app.route("/api/animeheaven/episodes/<path:anime_id>")
def ah_episodes_route(anime_id): return jsonify(ah_get_episodes(anime_id))

@app.route("/api/stream/<ep_hash>")
@limiter.limit("20 per minute")
def stream(ep_hash):
    log_visitor(request, "watch", "Stream hash: %s" % ep_hash)
    url = ah_get_stream_url(ep_hash)
    if url: return jsonify({"url": url, "status": "ok"})
    return jsonify({"url": None, "status": "error", "message": "Stream not found"})

@app.route("/api/proxy-stream")
@limiter.limit("10 per minute")
def proxy_stream():
    url = request.args.get("url", "")
    if not url or not validate_url(url):
        return jsonify({"error": "Invalid or missing URL"}), 400
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://animeheaven.me/gate.php", "Accept": "video/*;q=0.9,*/*;q=0.8"}
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type=r.headers.get("Content-Type", "video/mp4"), headers={"Accept-Ranges": "bytes", "Content-Length": r.headers.get("Content-Length", ""), "Connection": "keep-alive", "Cache-Control": "public, max-age=3600"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/download")
@limiter.limit(SecurityConfig.RATE_LIMIT_DOWNLOAD)
def download():
    url = request.args.get("url", "")
    filename = sanitize_filename(request.args.get("filename", "episode.mp4"))
    log_visitor(request, "download", "Downloaded: %s" % filename)
    quality = request.args.get("quality", "original")
    if not url or not validate_url(url):
        return jsonify({"error": "Invalid or missing URL"}), 400
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://animeheaven.me/gate.php"}
        if quality == "original" or quality not in ["720p", "480p", "360p"]:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": "attachment; filename=%s" % filename, "Content-Length": r.headers.get("Content-Length", "")})
        if not FFMPEG_AVAILABLE:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": "attachment; filename=%s" % filename, "Content-Length": r.headers.get("Content-Length", "")})
        scale_map = {"720p": "1280:720", "480p": "854:480", "360p": "640:360"}
        scale = scale_map.get(quality, "1280:720")
        temp_dir = "/tmp/kyro_" + str(os.getpid())
        os.makedirs(temp_dir, exist_ok=True)
        temp_input = os.path.join(temp_dir, "input.mp4")
        temp_output = os.path.join(temp_dir, "out_%s.mp4" % quality)
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            total_size = 0
            max_size = 500 * 1024 * 1024
            with open(temp_input, "wb") as f:
                for chunk in r.iter_content(chunk_size=262144):
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise Exception("Video too large for free tier transcoding (limit: 500MB)")
                    f.write(chunk)
            cmd = ["ffmpeg", "-y", "-i", temp_input, "-vf", "scale=%s" % scale, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", temp_output]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                raise Exception("ffmpeg transcoding failed")
            if not os.path.exists(temp_output) or os.path.getsize(temp_output) < 1024:
                raise Exception("ffmpeg output file is empty")
            def generate():
                with open(temp_output, "rb") as f:
                    while True:
                        chunk = f.read(262144)
                        if not chunk: break
                        yield chunk
                try:
                    os.remove(temp_input); os.remove(temp_output); os.rmdir(temp_dir)
                except: pass
            return Response(generate(), content_type="video/mp4", headers={"Content-Disposition": "attachment; filename=%s" % filename.replace(".mp4", "_%s.mp4" % quality)})
        except Exception as transcode_err:
            try:
                if os.path.exists(temp_input): os.remove(temp_input)
                if os.path.exists(temp_output): os.remove(temp_output)
                if os.path.exists(temp_dir): os.rmdir(temp_dir)
            except: pass
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": "attachment; filename=%s" % filename, "Content-Length": r.headers.get("Content-Length", "")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== ADMIN PAGES =====
@app.route("/admin/logs")
@require_role("staff")
def admin_logs():
    try:
        if not os.path.exists(VISITOR_LOG):
            return "<h1>No logs yet</h1><p>Wait for visitors...</p>"
        with open(VISITOR_LOG, "r") as f:
            logs = json.load(f)
        html = """<!DOCTYPE html><html><head><meta charset=utf-8>
        <title>KYRO Visitor Logs</title>
        <style>
        body{font-family:monospace;background:#0a0f2e;color:#e3f2fd;padding:20px}
        h1{color:#2962ff}table{width:100%;border-collapse:collapse;font-size:12px}
        th{background:#2962ff;color:#fff;padding:8px;text-align:left;position:sticky;top:0}
        td{padding:6px 8px;border-bottom:1px solid #1a237e}
        tr:hover{background:rgba(41,98,255,0.1)}
        .time{color:#90a4ae;width:160px}
        .device{color:#ffd600}
        .browser{color:#448aff}
        .action{color:#00d26a;font-weight:bold}
        .details{color:#b0bec5}
        .count{position:fixed;top:20px;right:20px;background:#2962ff;padding:10px 20px;border-radius:8px;font-weight:bold}
        </style></head><body>
        <h1>KYRO Visitor Logs</h1>
        <div class="count">Total Visits: %d</div>
        <table>
        <tr><th>Time</th><th>IP</th><th>Device</th><th>OS</th><th>Browser</th><th>Type</th><th>Action</th><th>Details</th></tr>""" % len(logs)
        for entry in reversed(logs[-200:]):
            device_type = "Phone" if entry.get("is_mobile") else "PC" if entry.get("is_pc") else "Tablet" if entry.get("is_tablet") else "?"
            html += """<tr>
                <td class="time">%s</td>
                <td>%s</td>
                <td class="device">%s %s</td>
                <td>%s</td>
                <td class="browser">%s</td>
                <td>%s</td>
                <td class="action">%s</td>
                <td class="details">%s</td>
            </tr>""" % (
                entry.get("timestamp", "")[:19],
                entry.get("ip", ""),
                device_type, entry.get("device", "Unknown"),
                entry.get("os", ""),
                entry.get("browser", ""),
                "Mobile" if entry.get("is_mobile") else "PC" if entry.get("is_pc") else "Tablet" if entry.get("is_tablet") else "Unknown",
                entry.get("action", ""),
                entry.get("details", "")
            )
        html += "</table></body></html>"
        return html
    except Exception as e:
        return "<h1>Error</h1><p>%s</p>" % e

@app.route("/admin/logs-json")
@require_role("staff")
def admin_logs_json():
    try:
        if not os.path.exists(VISITOR_LOG):
            return jsonify({"visits": [], "total": 0})
        with open(VISITOR_LOG, "r") as f:
            logs = json.load(f)
        return jsonify({"visits": logs, "total": len(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/dashboard")
@require_role("staff")
def admin_dashboard():
    try:
        with open("templates/dashboard.html", "r") as f:
            html = f.read()
        return render_template_string(html)
    except:
        return "<h1>Dashboard not found</h1><p>Make sure dashboard.html exists in templates/</p>", 404

# ===== ADMIN API =====

def get_stats():
    if not os.path.exists(VISITOR_LOG):
        return {"total_visits": 0, "searches": 0, "watches": 0, "downloads": 0, "chats": 0,
                "top_search": "None", "top_device": "Unknown", "active_now": 0,
                "top_searches": [], "device_breakdown": {}}
    try:
        with open(VISITOR_LOG, "r") as f:
            logs = json.load(f)
    except:
        return {"total_visits": 0, "searches": 0, "watches": 0, "downloads": 0, "chats": 0,
                "top_search": "None", "top_device": "Unknown", "active_now": 0,
                "top_searches": [], "device_breakdown": {}}
    searches = [e for e in logs if e.get("action") == "search"]
    watches = [e for e in logs if e.get("action") == "watch"]
    downloads = [e for e in logs if e.get("action") == "download"]
    chats = [e for e in logs if e.get("action") == "chat"]
    search_queries = {}
    for s in searches:
        q = s.get("details", "").replace("Searched for: ", "").strip()
        if q:
            search_queries[q] = search_queries.get(q, 0) + 1
    top_searches = sorted(search_queries.items(), key=lambda x: -x[1])[:15]
    devices = {}
    for e in logs:
        d = e.get("device", "Unknown")
        if d and d != "Unknown":
            devices[d] = devices.get(d, 0) + 1
    now = datetime.now()
    active = sum(1 for e in logs if e.get("timestamp") and 
                 (now - datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))).total_seconds() < 300)
    return {
        "total_visits": len(logs), "searches": len(searches), "watches": len(watches),
        "downloads": len(downloads), "chats": len(chats),
        "top_search": top_searches[0][0] if top_searches else "None",
        "top_device": max(devices, key=devices.get) if devices else "Unknown",
        "active_now": active, "top_searches": top_searches, "device_breakdown": devices
    }

@app.route("/admin/api/status")
@require_role("staff")
@limiter.limit(SecurityConfig.RATE_LIMIT_ADMIN)
def admin_api_status():
    try:
        ah_ok = requests.get(ANIMEHEAVEN, timeout=10).status_code == 200
    except:
        ah_ok = False
    try:
        anilist_ok = requests.post(ANILIST_URL, json={"query": "{Page(page:1,perPage:1){media(type:ANIME){id}}}", "variables": {}}, timeout=10).status_code == 200
    except:
        anilist_ok = False
    stats = get_stats()
    return jsonify({
        "server_up": True,
        "animeheaven": "connected" if ah_ok else "disconnected",
        "anilist": "connected" if anilist_ok else "disconnected",
        "groq": "connected" if SecurityConfig.GROQ_API_KEY else "no_key",
        "ffmpeg": "available" if FFMPEG_AVAILABLE else "not_installed",
        "total_visits": stats["total_visits"],
        "active_now": stats["active_now"],
        "stats": stats,
        "top_searches": stats["top_searches"],
        "device_breakdown": stats["device_breakdown"],
        "user_role": g.user_role
    })

@app.route("/admin/api/live")
@require_role("staff")
@limiter.limit(SecurityConfig.RATE_LIMIT_ADMIN)
def admin_api_live():
    stats = get_stats()
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, "r") as f:
                logs = json.load(f)
        except:
            pass
    return jsonify({"total": stats["total_visits"], "active_now": stats["active_now"], "recent": logs[-50:] if logs else []})

@app.route("/admin/api/searches")
@require_role("staff")
@limiter.limit(SecurityConfig.RATE_LIMIT_ADMIN)
def admin_api_searches():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, "r") as f:
                logs = json.load(f)
        except:
            pass
    searches = [e for e in logs if e.get("action") == "search"]
    search_queries = {}
    for s in searches:
        q = s.get("details", "").replace("Searched for: ", "").strip()
        if q:
            search_queries[q] = search_queries.get(q, 0) + 1
    return jsonify({"searches": searches, "total_searches": len(searches), "top_searches": sorted(search_queries.items(), key=lambda x: -x[1])[:20]})

@app.route("/admin/api/downloads")
@require_role("staff")
@limiter.limit(SecurityConfig.RATE_LIMIT_ADMIN)
def admin_api_downloads():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, "r") as f:
                logs = json.load(f)
        except:
            pass
    downloads = [e for e in logs if e.get("action") == "download"]
    return jsonify({"downloads": downloads, "total_downloads": len(downloads)})

@app.route("/admin/api/chats")
@require_role("staff")
@limiter.limit(SecurityConfig.RATE_LIMIT_ADMIN)
def admin_api_chats():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, "r") as f:
                logs = json.load(f)
        except:
            pass
    chats = [e for e in logs if e.get("action") == "chat"]
    return jsonify({"chats": chats, "total_chats": len(chats)})

# ===== BROADCAST =====
BROADCAST_MESSAGES = []

@app.route("/admin/api/broadcast", methods=["POST"])
@require_role("staff")
@limiter.limit("10 per minute")
def admin_api_broadcast():
    data = request.get_json() or {}
    msg = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "Message required"}), 400
    entry = {"timestamp": datetime.now().isoformat(), "message": sanitize_html(msg), "id": len(BROADCAST_MESSAGES), "sent_by": g.user_role}
    BROADCAST_MESSAGES.append(entry)
    if len(BROADCAST_MESSAGES) > 50:
        BROADCAST_MESSAGES.pop(0)
    log_security_event("BROADCAST_SENT", "Message by %s" % g.user_role, severity="info")
    return jsonify({"sent_to": get_stats().get("active_now", 0), "message": msg})

@app.route("/admin/api/broadcasts")
def admin_api_broadcasts():
    return jsonify({"messages": BROADCAST_MESSAGES[-5:]})

# ===== SERVER CONTROL =====
SERVER_STOPPED = False

@app.route("/admin/api/start", methods=["POST"])
@require_role("owner")
def admin_api_start():
    global SERVER_STOPPED
    SERVER_STOPPED = False
    log_security_event("SERVER_STARTED", "Server brought online by owner", severity="info")
    return jsonify({"status": "started", "message": "Server is now online"})

@app.route("/admin/api/stop", methods=["POST"])
@require_role("owner")
def admin_api_stop():
    global SERVER_STOPPED
    SERVER_STOPPED = True
    log_security_event("SERVER_STOPPED", "Server stopped by owner", severity="warning")
    return jsonify({"status": "stopped", "message": "Server stopping... Visitors will see maintenance page"})

@app.route("/admin/api/restart", methods=["POST"])
@require_role("owner")
def admin_api_restart():
    global SERVER_STOPPED
    SERVER_STOPPED = False
    BROADCAST_MESSAGES.clear()
    log_security_event("SERVER_RESTARTED", "Server restarted by owner", severity="info")
    return jsonify({"status": "restarting", "message": "Server restart initiated"})

@app.route("/admin/api/server-status")
def admin_api_server_status():
    return jsonify({"running": not SERVER_STOPPED, "maintenance": SERVER_STOPPED, "broadcasts": BROADCAST_MESSAGES[-3:]})

# ===== AI ERROR ANALYSIS =====

@app.route("/admin/api/errors")
@require_role("owner")
def admin_api_errors():
    errors = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r") as f:
                errors = json.load(f)
        except:
            pass
    return jsonify({"errors": errors[-50:], "total": len(errors), "unanalyzed": sum(1 for e in errors if not e.get("analyzed"))})

@app.route("/admin/api/errors/analyze", methods=["POST"])
@require_role("owner")
def admin_api_analyze_errors():
    errors = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r") as f:
                errors = json.load(f)
        except:
            pass
    unanalyzed = [e for e in errors if not e.get("analyzed")]
    if not unanalyzed:
        return jsonify({"message": "No new errors to analyze", "results": []})
    results = []
    for error in unanalyzed[:5]:
        ai_result = analyze_error_with_ai(error)
        error["analyzed"] = True
        error["ai_diagnosis"] = ai_result["diagnosis"]
        error["ai_fix"] = ai_result["fix"]
        results.append({
            "timestamp": error["timestamp"],
            "type": error["type"],
            "message": error["message"],
            "diagnosis": ai_result["diagnosis"],
            "fix": ai_result["fix"]
        })
    with open(ERROR_LOG, "w") as f:
        json.dump(errors, f, indent=2)
    return jsonify({"results": results, "remaining": sum(1 for e in errors if not e.get("analyzed"))})

@app.route("/admin/api/ai/code-review", methods=["POST"])
@require_role("owner")
def admin_api_code_review():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    issue = data.get("issue", "").strip()
    if not code and not issue:
        return jsonify({"error": "Provide code or describe an issue"}), 400
    if not SecurityConfig.AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    prompt = "You are a senior Python/Flask developer. Review this code and provide fixes.\n\n"
    if issue:
        prompt += "Issue reported: %s\n\n" % issue
    if code:
        prompt += "Code to review:\n```python\n%s\n```\n\n" % code[:3000]
    prompt += "Provide:\n1. PROBLEM: What is wrong\n2. FIX: The corrected code\n3. EXPLANATION: Why this fixes it\n\nKeep it concise and actionable."
    try:
        payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 2048}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer %s" % SecurityConfig.AI_ERROR_KEY, "Content-Type": "application/json"},
            json=payload, timeout=45)
        result = r.json()
        if "choices" in result:
            return jsonify({"review": result["choices"][0]["message"]["content"]})
        return jsonify({"error": "AI returned no response"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/ai/ask", methods=["POST"])
@require_role("owner")
def admin_api_ai_ask():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question required"}), 400
    if not SecurityConfig.AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    stats = get_stats()
    context = """Current KYRO site stats:
- Total visits: %d
- Active now: %d
- Searches today: %d
- Watches today: %d
- Downloads today: %d
- Top search: %s
- Server: %s
- AnimeHeaven: %s
- AniList: Connected
- AI Chat: %s
""" % (
        stats["total_visits"], stats["active_now"], stats["searches"],
        stats["watches"], stats["downloads"], stats["top_search"],
        "Running" if not SERVER_STOPPED else "STOPPED (maintenance)",
        "Connected" if get_ah_status() else "Down",
        "Enabled" if SecurityConfig.GROQ_API_KEY else "Disabled (no key)"
    )
    prompt = """You are KYRO's AI assistant. Help the site owner manage their anime website.

%s

Owner's question: %s

Answer concisely and helpfully.
""" % (context, question)
    try:
        payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 1024}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer %s" % SecurityConfig.AI_ERROR_KEY, "Content-Type": "application/json"},
            json=payload, timeout=30)
        result = r.json()
        if "choices" in result:
            return jsonify({"answer": result["choices"][0]["message"]["content"]})
        return jsonify({"error": "AI returned no response"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/api/ai/diagnose-site", methods=["POST"])
@require_role("owner")
def admin_api_diagnose_site():
    if not SecurityConfig.AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    stats = get_stats()
    errors = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r") as f:
                errors = json.load(f)
        except:
            pass
    recent_errors = errors[-10:]
    error_summary = ""
    for e in recent_errors:
        error_summary += "- [%s] %s: %s\n" % (e.get("timestamp", ""), e.get("type", ""), e.get("message", "")[:80])
    prompt = """You are a site health expert. Analyze this anime streaming website and give actionable recommendations.

SITE STATS:
- Total visits: %d
- Active now: %d
- Searches: %d
- Watches: %d
- Downloads: %d
- Top search: %s
- Device breakdown: %s

RECENT ERRORS:
%s

Provide:
1. HEALTH SCORE: Rate 1-10
2. ISSUES: Any problems detected
3. RECOMMENDATIONS: 3 specific things to improve
4. PRIORITY: What to fix first

Be direct and actionable.""" % (
        stats["total_visits"], stats["active_now"], stats["searches"],
        stats["watches"], stats["downloads"], stats["top_search"],
        str(dict(list(stats["device_breakdown"].items())[:5])),
        error_summary if error_summary else "No recent errors"
    )
    try:
        payload = {"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.5, "max_tokens": 1500}
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer %s" % SecurityConfig.AI_ERROR_KEY, "Content-Type": "application/json"},
            json=payload, timeout=30)
        result = r.json()
        if "choices" in result:
            return jsonify({"diagnosis": result["choices"][0]["message"]["content"]})
        return jsonify({"error": "AI returned no response"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== SECURITY DASHBOARD =====
@app.route("/admin/security-logs")
@require_role("owner")
def admin_security_logs():
    try:
        if not os.path.exists(SECURITY_LOG):
            return jsonify({"events": [], "total": 0})
        with open(SECURITY_LOG, "r") as f:
            logs = json.load(f)
        # Verify integrity of recent logs
        verified = []
        for entry in logs[-100:]:
            integrity_copy = entry.pop("integrity", "")
            computed = sign_data(json.dumps(entry, sort_keys=True, default=str))
            entry["integrity_valid"] = hmac.compare_digest(computed, integrity_copy)
            entry["integrity"] = integrity_copy
            verified.append(entry)
        return jsonify({"events": verified, "total": len(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Render sets PORT env var automatically
    port = int(os.environ.get("PORT", 5000))
    # Production: never run with debug=True
    app.run(debug=False, host="0.0.0.0", port=port)
