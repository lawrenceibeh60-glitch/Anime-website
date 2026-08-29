from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context, send_from_directory, g
from flask_cors import CORS
import requests
import os
import re
import subprocess
import traceback
import hashlib
import secrets
import string
from bs4 import BeautifulSoup
from datetime import datetime
from user_agents import parse as ua_parse
import json

# ===== PASSWORD & UNLOCK SYSTEM =====
# Default password (change this!)
DEFAULT_PASSWORD = os.environ.get("KYRO_PASSWORD", "kyro2026")
# Max failed attempts before lockout
MAX_ATTEMPTS = 5
# Store failed attempts per IP
FAILED_ATTEMPTS = {}
# Unlock codes sent by locked-out users
UNLOCK_CODES = []
# Current password (can be changed by admin)
CURRENT_PASSWORD = DEFAULT_PASSWORD

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def check_password(pwd):
    return hash_password(pwd) == hash_password(CURRENT_PASSWORD)

def generate_unlock_code():
    """Generate a 6-digit unlock code"""
    return "".join(secrets.choice(string.digits) for _ in range(6))

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'

def is_locked_out(ip):
    if ip not in FAILED_ATTEMPTS:
        return False
    return FAILED_ATTEMPTS[ip] >= MAX_ATTEMPTS

def record_failed_attempt(ip):
    FAILED_ATTEMPTS[ip] = FAILED_ATTEMPTS.get(ip, 0) + 1

def reset_attempts(ip):
    if ip in FAILED_ATTEMPTS:
        del FAILED_ATTEMPTS[ip]

def get_remaining_attempts(ip):
    return max(0, MAX_ATTEMPTS - FAILED_ATTEMPTS.get(ip, 0))

# ===== ERROR CATCHING & AI LOGGING =====
ERROR_LOG = "/tmp/kyro_errors.json"
AI_ERROR_QUEUE = []

# AI Config for error analysis
AI_ERROR_KEY = os.environ.get("AI_ERROR_KEY", os.environ.get("GROQ_API_KEY", ""))
AI_MODEL = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")

# Fallback models in order of reliability (if primary fails)
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "mixtral-8x7b-32768"
]

def groq_chat_completion(messages, system_prompt=None, temperature=0.7, max_tokens=1024, timeout=30):
    """Send chat to Groq with automatic fallback between models"""
    if not GROQ_API_KEY:
        return {"error": "No GROQ_API_KEY configured", "reply": "Set your GROQ_API_KEY environment variable to enable AI chat."}
    
    all_models = [AI_MODEL] + [m for m in FALLBACK_MODELS if m != AI_MODEL]
    last_error = None
    
    for model in all_models:
        try:
            payload = {
                "model": model,
                "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout
            )
            result = r.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                return {"success": True, "reply": result["choices"][0]["message"]["content"], "model_used": model}
            elif "error" in result:
                err_msg = result["error"].get("message", "Unknown error")
                # If model not found, try next
                if "model" in err_msg.lower() or "not found" in err_msg.lower():
                    last_error = err_msg
                    continue
                return {"error": err_msg, "reply": f"Groq API Error: {err_msg}"}
            else:
                last_error = "Unexpected response format"
                continue
                
        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            continue
        except Exception as e:
            last_error = str(e)
            continue
    
    # All models failed
    return {"error": f"All models failed. Last error: {last_error}", "reply": "AI service is temporarily unavailable. Please try again in a moment."}

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
                with open(ERROR_LOG, 'r') as f:
                    errors = json.load(f)
            except:
                pass
        errors.append(entry)
        errors = errors[-200:]
        with open(ERROR_LOG, 'w') as f:
            json.dump(errors, f, indent=2)
        AI_ERROR_QUEUE.append(entry)
        if len(AI_ERROR_QUEUE) > 50:
            AI_ERROR_QUEUE.pop(0)
        print(f"[KYRO ERROR] {error_type}: {str(error_msg)[:100]}")
    except Exception as e:
        print(f"[KYRO ERROR LOGGING FAILED] {e}")

def analyze_error_with_ai(error_entry):
    if not AI_ERROR_KEY:
        return {"diagnosis": "No AI key configured. Set AI_ERROR_KEY env var.", "fix": "N/A"}
    prompt = f"""You are a Python/Flask debugging expert. Analyze this error and provide:
1. A clear diagnosis (what went wrong in 1-2 sentences)
2. A specific code fix (the exact code change needed)

Error Type: {error_entry['type']}
Error Message: {error_entry['message']}
Endpoint: {error_entry['endpoint']}
Traceback:
{error_entry['traceback']}

Respond in this exact format:
DIAGNOSIS: [your diagnosis here]
FIX: [your code fix here]
"""
    result = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024
    )
    if result.get("success"):
        text = result["reply"]
        diagnosis = ""
        fix = ""
        if "DIAGNOSIS:" in text:
            parts = text.split("FIX:")
            diagnosis = parts[0].replace("DIAGNOSIS:", "").strip()
            fix = parts[1].strip() if len(parts) > 1 else "See full response"
        else:
            diagnosis = text[:200]
            fix = text[200:500] if len(text) > 200 else "N/A"
        return {"diagnosis": diagnosis, "fix": fix, "full_response": text, "model_used": result.get("model_used")}
    return {"diagnosis": f"AI analysis failed: {result.get('error', 'Unknown')}", "fix": "N/A"}

# ===== VISITOR TRACKING =====
VISITOR_LOG = "/tmp/kyro_visitors.json"

def log_visitor(request, action="page_view", details=""):
    try:
        ua_string = request.headers.get('User-Agent', '')
        ua = ua_parse(ua_string)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'
        entry = {
            "timestamp": datetime.now().isoformat(),
            "ip": ip.split(',')[0].strip() if ',' in ip else ip,
            "device": ua.device.family or "Unknown",
            "brand": ua.device.brand or "Unknown",
            "model": ua.device.model or "Unknown",
            "os": f"{ua.os.family} {ua.os.version_string}" if ua.os.version_string else ua.os.family,
            "browser": f"{ua.browser.family} {ua.browser.version_string}" if ua.browser.version_string else ua.browser.family,
            "is_mobile": ua.is_mobile,
            "is_tablet": ua.is_tablet,
            "is_pc": ua.is_pc,
            "action": action,
            "details": details,
            "path": request.path
        }
        logs = []
        if os.path.exists(VISITOR_LOG):
            try:
                with open(VISITOR_LOG, 'r') as f:
                    logs = json.load(f)
            except:
                pass
        logs.append(entry)
        logs = logs[-5000:]
        with open(VISITOR_LOG, 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"[KYRO LOG ERROR] {e}")

# ===== ROLE-BASED API KEYS =====
OWNER_KEY = os.environ.get("KYRO_OWNER_KEY", "")
STAFF_KEY = os.environ.get("KYRO_STAFF_KEY", "")

def get_role_from_key(key):
    if OWNER_KEY and key == OWNER_KEY:
        return "owner"
    if STAFF_KEY and key == STAFF_KEY:
        return "staff"
    return None

def require_role(min_role="staff"):
    def decorator(f):
        def wrapper(*args, **kwargs):
            key = request.headers.get("X-Admin-Key", "")
            role = get_role_from_key(key)
            if not role:
                return jsonify({"error": "Invalid or missing admin key"}), 403
            if min_role == "owner" and role != "owner":
                return jsonify({"error": "Owner access required"}), 403
            g.user_role = role
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ===== FFMPEG =====
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        FFMPEG_AVAILABLE = True
except:
    pass

# ===== FLASK APP =====
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/admin/*": {"origins": "*"}})

# Error handler
@app.errorhandler(Exception)
def handle_error(error):
    tb = traceback.format_exc()
    log_error(type(error).__name__, str(error), tb,
              endpoint=request.path, user_agent=request.headers.get('User-Agent', ''))
    return jsonify({"error": "Internal server error", "type": type(error).__name__}), 500

# Request hooks
@app.before_request
def before_request():
    g.start_time = datetime.now()

@app.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        duration = (datetime.now() - g.start_time).total_seconds()
        if duration > 5:
            log_error("SLOW_REQUEST", f"Request took {duration:.1f}s",
                      f"Endpoint: {request.path}\nMethod: {request.method}",
                      endpoint=request.path)
        if response.status_code >= 500:
            log_error("HTTP_500", f"Status {response.status_code}",
                      f"Endpoint: {request.path}", endpoint=request.path)
    return response

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ANILIST_URL = "https://graphql.anilist.co"
ANIMEHEAVEN = "https://animeheaven.me"

SYSTEM_PROMPT = """You are KYRO, an AI anime expert."""

# ===== PASSWORD API ENDPOINTS =====

@app.route("/api/password/check", methods=["POST"])
def password_check():
    """Check if password is correct, track attempts"""
    data = request.get_json() or {}
    pwd = data.get("password", "")
    ip = get_client_ip()

    if is_locked_out(ip):
        return jsonify({"locked": True, "message": "Too many failed attempts. Contact admin for unlock code."}), 403

    if check_password(pwd):
        reset_attempts(ip)
        return jsonify({"success": True, "role": "user"})
    else:
        record_failed_attempt(ip)
        remaining = get_remaining_attempts(ip)
        return jsonify({"success": False, "remaining": remaining, "locked": remaining == 0})

@app.route("/api/password/remaining")
def password_remaining():
    """Get remaining attempts for this IP"""
    ip = get_client_ip()
    return jsonify({
        "remaining": get_remaining_attempts(ip),
        "locked": is_locked_out(ip)
    })

@app.route("/api/password/unlock-request", methods=["POST"])
def password_unlock_request():
    """User is locked out, send unlock code to admin"""
    data = request.get_json() or {}
    ip = get_client_ip()
    device = data.get("device", "Unknown")

    code = generate_unlock_code()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "code": code,
        "ip": ip,
        "device": device,
        "used": False
    }
    UNLOCK_CODES.append(entry)
    if len(UNLOCK_CODES) > 100:
        UNLOCK_CODES.pop(0)

    return jsonify({"success": True, "message": "Unlock request sent to admin. Wait for admin to unlock you."})

@app.route("/admin/api/unlock-codes")
@require_role("owner")
def admin_unlock_codes():
    """Admin views all pending unlock codes"""
    pending = [u for u in UNLOCK_CODES if not u.get("used")]
    return jsonify({"codes": pending, "total_pending": len(pending)})

@app.route("/admin/api/unlock", methods=["POST"])
@require_role("owner")
def admin_unlock():
    """Admin unlocks a user and optionally sets new password"""
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    new_password = data.get("new_password", "").strip()

    # Find and mark code as used
    found = False
    for u in UNLOCK_CODES:
        if u.get("code") == code and not u.get("used"):
            u["used"] = True
            found = True
            # Reset attempts for that IP
            reset_attempts(u.get("ip", ""))
            break

    if not found:
        return jsonify({"error": "Invalid or used unlock code"}), 400

    # Optionally change password
    global CURRENT_PASSWORD
    if new_password and len(new_password) >= 4:
        CURRENT_PASSWORD = new_password
        return jsonify({"success": True, "message": "User unlocked and password changed."})

    return jsonify({"success": True, "message": "User unlocked. Password unchanged."})

@app.route("/admin/api/change-password", methods=["POST"])
@require_role("owner")
def admin_change_password():
    """Admin changes the password directly"""
    global CURRENT_PASSWORD
    data = request.get_json() or {}
    new_password = data.get("new_password", "").strip()

    if not new_password or len(new_password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400

    CURRENT_PASSWORD = new_password
    return jsonify({"success": True, "message": "Password updated successfully."})

# ===== ANILIST FUNCTIONS =====
def anilist_search(query, limit=20):
    q = """query ($search: String, $perPage: Int) { Page(page: 1, perPage: $perPage) { media(search: $search, type: ANIME) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status } } }"""
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"search": query, "perPage": limit}}, timeout=15)
    data = r.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])
    results = []
    for m in media:
        results.append({"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:300], "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"]})
    return results

def anilist_trending(limit=20):
    q = """query ($perPage: Int) { Page(page: 1, perPage: $perPage) { media(type: ANIME, sort: TRENDING_DESC) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status } } }"""
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"perPage": limit}}, timeout=15)
    data = r.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])
    results = []
    for m in media:
        results.append({"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", "")[:300], "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"]})
    return results

def anilist_detail(anime_id):
    q = """query ($id: Int) { Media(id: $id, type: ANIME) { id title { romaji english native } coverImage { large medium } episodes averageScore description genres seasonYear status trailer { id site } } }"""
    r = requests.post(ANILIST_URL, json={"query": q, "variables": {"id": anime_id}}, timeout=15)
    data = r.json()
    m = data.get("data", {}).get("Media", {})
    return {"id": m["id"], "title": m["title"]["romaji"] or m["title"]["native"], "title_english": m["title"]["english"], "image": m["coverImage"]["large"] or m["coverImage"]["medium"], "episodes": m["episodes"], "score": m["averageScore"], "synopsis": (m["description"] or "").replace("<br>", " ").replace("<i>", "").replace("</i>", ""), "genres": m["genres"] or [], "year": m["seasonYear"], "status": m["status"], "trailer": m.get("trailer", {}).get("id", "")}

# ===== ANIMEHEAVEN FUNCTIONS =====
def ah_get_episodes(anime_id):
    try:
        r = requests.get(f"{ANIMEHEAVEN}/anime.php?{anime_id}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": ANIMEHEAVEN}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        title, image, desc = "", "", ""
        h1 = soup.find("h1")
        if h1: title = h1.get_text(strip=True)
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "image.php" in src: image = src if src.startswith("http") else f"{ANIMEHEAVEN}/{src}"; break
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
                    episodes.append({"hash": ep_hash, "number": ep_num, "title": f"Episode {ep_num}", "anime_id": anime_id})
        return {"title": title, "image": image, "description": desc, "episodes": episodes}
    except Exception as e:
        return {"error": str(e), "episodes": []}

def ah_get_stream_url(ep_hash):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": f"{ANIMEHEAVEN}/anime.php"})
        session.cookies.set("key", ep_hash, domain="animeheaven.me")
        r = session.get(f"{ANIMEHEAVEN}/gate.php", timeout=15)
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
        r = requests.get(f"{ANIMEHEAVEN}/search.php", params={"s": query}, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": ANIMEHEAVEN}, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "anime.php" in href:
                anime_id = href.split("?")[-1]
                title = a.get_text(strip=True)
                if title and anime_id: results.append({"id": anime_id, "title": title, "url": f"{ANIMEHEAVEN}/{href}"})
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
        "groq": "connected" if GROQ_API_KEY else "no_key",
        "ffmpeg": "available" if FFMPEG_AVAILABLE else "not_installed"
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("messages", [{}])[-1].get("content", "") if data.get("messages") else ""
    log_visitor(request, "chat", f"Chat message: {msg[:50]}...")
    messages = data.get("messages", [])
    result = groq_chat_completion(messages, system_prompt=SYSTEM_PROMPT, temperature=0.8, max_tokens=1024)
    return jsonify({"reply": result.get("reply", "AI service unavailable")})

@app.route("/api/search")
def search():
    q = request.args.get("q", "")
    if q:
        log_visitor(request, "search", f"Searched for: {q}")
    if not q: return jsonify({"results": anilist_trending(20)})
    try: return jsonify({"results": anilist_search(q, 20)})
    except Exception as e: return jsonify({"results": [], "error": str(e)})

@app.route("/api/anime/<int:anime_id>")
def anime_detail(anime_id):
    log_visitor(request, "view_anime", f"Viewed anime ID: {anime_id}")
    try: return jsonify(anilist_detail(anime_id))
    except Exception as e: return jsonify({"error": str(e)})

@app.route("/api/animeheaven/search")
def ah_search_route():
    q = request.args.get("q", "")
    if not q: return jsonify({"results": []})
    return jsonify({"results": ah_search_anime(q)})

@app.route("/api/animeheaven/episodes/<path:anime_id>")
def ah_episodes_route(anime_id): return jsonify(ah_get_episodes(anime_id))

@app.route("/api/stream/<ep_hash>")
def stream(ep_hash):
    log_visitor(request, "watch", f"Stream hash: {ep_hash}")
    url = ah_get_stream_url(ep_hash)
    if url: return jsonify({"url": url, "status": "ok"})
    return jsonify({"url": None, "status": "error", "message": "Stream not found"})

@app.route("/api/proxy-stream")
def proxy_stream():
    url = request.args.get("url", "")
    if not url: return jsonify({"error": "No URL"}), 400
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://animeheaven.me/gate.php", "Accept": "video/*;q=0.9,*/*;q=0.8"}
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type=r.headers.get("Content-Type", "video/mp4"), headers={"Accept-Ranges": "bytes", "Content-Length": r.headers.get("Content-Length", ""), "Connection": "keep-alive", "Cache-Control": "public, max-age=3600"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/download")
def download():
    url = request.args.get("url", "")
    filename = request.args.get("filename", "episode.mp4")
    log_visitor(request, "download", f"Downloaded: {filename}")
    quality = request.args.get("quality", "original")
    if not url: return jsonify({"error": "No URL"}), 400
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://animeheaven.me/gate.php"}
        if quality == "original" or quality not in ["720p", "480p", "360p"]:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
        if not FFMPEG_AVAILABLE:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
        scale_map = {"720p": "1280:720", "480p": "854:480", "360p": "640:360"}
        scale = scale_map.get(quality, "1280:720")
        temp_dir = "/tmp/kyro_" + str(os.getpid())
        os.makedirs(temp_dir, exist_ok=True)
        temp_input = os.path.join(temp_dir, "input.mp4")
        temp_output = os.path.join(temp_dir, f"out_{quality}.mp4")
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
            cmd = ["ffmpeg", "-y", "-i", temp_input, "-vf", f"scale={scale}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", temp_output]
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
            return Response(generate(), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename.replace('.mp4', f'_{quality}.mp4')}"})
        except Exception as transcode_err:
            try:
                if os.path.exists(temp_input): os.remove(temp_input)
                if os.path.exists(temp_output): os.remove(temp_output)
                if os.path.exists(temp_dir): os.rmdir(temp_dir)
            except: pass
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== ADMIN PAGES =====
@app.route("/admin/logs")
def admin_logs():
    try:
        if not os.path.exists(VISITOR_LOG):
            return "<h1>No logs yet</h1><p>Wait for visitors...</p>"
        with open(VISITOR_LOG, 'r') as f:
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
        <div class="count">Total Visits: """ + str(len(logs)) + """</div>
        <table>
        <tr><th>Time</th><th>IP</th><th>Device</th><th>OS</th><th>Browser</th><th>Type</th><th>Action</th><th>Details</th></tr>"""
        for entry in reversed(logs[-200:]):
            device_type = "Phone" if entry.get('is_mobile') else "PC" if entry.get('is_pc') else "Tablet" if entry.get('is_tablet') else "?"
            html += f"""<tr>
                <td class="time">{entry.get('timestamp','')[:19]}</td>
                <td>{entry.get('ip','')}</td>
                <td class="device">{device_type} {entry.get('device','Unknown')}</td>
                <td>{entry.get('os','')}</td>
                <td class="browser">{entry.get('browser','')}</td>
                <td>{'Mobile' if entry.get('is_mobile') else 'PC' if entry.get('is_pc') else 'Tablet' if entry.get('is_tablet') else 'Unknown'}</td>
                <td class="action">{entry.get('action','')}</td>
                <td class="details">{entry.get('details','')}</td>
            </tr>"""
        html += "</table></body></html>"
        return html
    except Exception as e:
        return f"<h1>Error</h1><p>{e}</p>"

@app.route("/admin/logs-json")
def admin_logs_json():
    try:
        if not os.path.exists(VISITOR_LOG):
            return jsonify({"visits": [], "total": 0})
        with open(VISITOR_LOG, 'r') as f:
            logs = json.load(f)
        return jsonify({"visits": logs, "total": len(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/dashboard")
def admin_dashboard():
    return send_from_directory('templates', 'dashboard.html')

# ===== ADMIN API =====

def get_stats():
    if not os.path.exists(VISITOR_LOG):
        return {"total_visits": 0, "searches": 0, "watches": 0, "downloads": 0, "chats": 0,
                "top_search": "None", "top_device": "Unknown", "active_now": 0,
                "top_searches": [], "device_breakdown": {}}
    try:
        with open(VISITOR_LOG, 'r') as f:
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
        "groq": "connected" if GROQ_API_KEY else "no_key",
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
def admin_api_live():
    stats = get_stats()
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, 'r') as f:
                logs = json.load(f)
        except:
            pass
    return jsonify({"total": stats["total_visits"], "active_now": stats["active_now"], "recent": logs[-50:] if logs else []})

@app.route("/admin/api/searches")
@require_role("staff")
def admin_api_searches():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, 'r') as f:
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
def admin_api_downloads():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, 'r') as f:
                logs = json.load(f)
        except:
            pass
    downloads = [e for e in logs if e.get("action") == "download"]
    return jsonify({"downloads": downloads, "total_downloads": len(downloads)})

@app.route("/admin/api/chats")
@require_role("staff")
def admin_api_chats():
    logs = []
    if os.path.exists(VISITOR_LOG):
        try:
            with open(VISITOR_LOG, 'r') as f:
                logs = json.load(f)
        except:
            pass
    chats = [e for e in logs if e.get("action") == "chat"]
    return jsonify({"chats": chats, "total_chats": len(chats)})

# ===== BROADCAST =====
BROADCAST_MESSAGES = []

@app.route("/admin/api/broadcast", methods=["POST"])
@require_role("staff")
def admin_api_broadcast():
    data = request.get_json() or {}
    msg = data.get("message", "").strip()
    if not msg:
        return jsonify({"error": "Message required"}), 400
    entry = {"timestamp": datetime.now().isoformat(), "message": msg, "id": len(BROADCAST_MESSAGES), "sent_by": g.user_role}
    BROADCAST_MESSAGES.append(entry)
    if len(BROADCAST_MESSAGES) > 50:
        BROADCAST_MESSAGES.pop(0)
    return jsonify({"sent_to": get_stats().get("active_now", 0), "message": msg})

@app.route("/admin/api/broadcasts")
def admin_api_broadcasts():
    return jsonify({"messages": BROADCAST_MESSAGES[-5:]})

# ===== SERVER CONTROL (OWNER ONLY) =====
SERVER_STOPPED = False

@app.route("/admin/api/start", methods=["POST"])
@require_role("owner")
def admin_api_start():
    global SERVER_STOPPED
    SERVER_STOPPED = False
    return jsonify({"status": "started", "message": "Server is now online"})

@app.route("/admin/api/stop", methods=["POST"])
@require_role("owner")
def admin_api_stop():
    global SERVER_STOPPED
    SERVER_STOPPED = True
    return jsonify({"status": "stopped", "message": "Server stopping... Visitors will see maintenance page"})

@app.route("/admin/api/restart", methods=["POST"])
@require_role("owner")
def admin_api_restart():
    global SERVER_STOPPED
    SERVER_STOPPED = False
    BROADCAST_MESSAGES.clear()
    return jsonify({"status": "restarting", "message": "Server restart initiated"})

@app.route("/admin/api/server-status")
def admin_api_server_status():
    return jsonify({"running": not SERVER_STOPPED, "maintenance": SERVER_STOPPED, "broadcasts": BROADCAST_MESSAGES[-3:]})

# ===== AI ERROR ANALYSIS (OWNER ONLY) =====

@app.route("/admin/api/errors")
@require_role("owner")
def admin_api_errors():
    errors = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, 'r') as f:
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
            with open(ERROR_LOG, 'r') as f:
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
    with open(ERROR_LOG, 'w') as f:
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
    if not AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    prompt = f"""You are a senior Python/Flask developer. Review this code and provide fixes.

"""
    if issue:
        prompt += f"Issue reported: {issue}\n\n"
    if code:
        prompt += f"Code to review:\n```python\n{code[:3000]}\n```\n\n"
    prompt += """Provide:
1. PROBLEM: What's wrong (be specific)
2. FIX: The corrected code
3. EXPLANATION: Why this fixes it

Keep it concise and actionable."""
    result = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048,
        timeout=45
    )
    if result.get("success"):
        return jsonify({"review": result["reply"], "model_used": result.get("model_used")})
    return jsonify({"error": result.get("error", "AI failed")}), 500

@app.route("/admin/api/ai/ask", methods=["POST"])
@require_role("owner")
def admin_api_ai_ask():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question required"}), 400
    if not AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    stats = get_stats()
    context = f"""Current KYRO site stats:
- Total visits: {stats['total_visits']}
- Active now: {stats['active_now']}
- Searches today: {stats['searches']}
- Watches today: {stats['watches']}
- Downloads today: {stats['downloads']}
- Top search: {stats['top_search']}
- Server: {'Running' if not SERVER_STOPPED else 'STOPPED (maintenance)'}
- AnimeHeaven: {'Connected' if requests.get(ANIMEHEAVEN, timeout=5).status_code == 200 else 'Down'}
- AniList: Connected
- AI Chat: {'Enabled' if GROQ_API_KEY else 'Disabled (no key)'}
"""
    prompt = f"""You are KYRO's AI assistant. Help the site owner manage their anime website.

{context}

Owner's question: {question}

Answer concisely and helpfully. If they ask about errors, check the stats above.
If they ask about features, suggest improvements based on the data.
"""
    result = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1024
    )
    if result.get("success"):
        return jsonify({"answer": result["reply"], "model_used": result.get("model_used")})
    return jsonify({"error": result.get("error", "AI failed")}), 500

@app.route("/admin/api/ai/diagnose-site", methods=["POST"])
@require_role("owner")
def admin_api_diagnose_site():
    if not AI_ERROR_KEY:
        return jsonify({"error": "AI_ERROR_KEY not configured"}), 500
    stats = get_stats()
    errors = []
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, 'r') as f:
                errors = json.load(f)
        except:
            pass
    recent_errors = errors[-10:]
    error_summary = ""
    for e in recent_errors:
        error_summary += f"- [{e.get('timestamp','')}] {e.get('type','')}: {e.get('message','')[:80]}\n"
    prompt = f"""You are a site health expert. Analyze this anime streaming website and give actionable recommendations.

SITE STATS:
- Total visits: {stats['total_visits']}
- Active now: {stats['active_now']}
- Searches: {stats['searches']}
- Watches: {stats['watches']}
- Downloads: {stats['downloads']}
- Top search: {stats['top_search']}
- Device breakdown: {dict(list(stats['device_breakdown'].items())[:5])}

RECENT ERRORS:
{error_summary if error_summary else 'No recent errors'}

Provide:
1. HEALTH SCORE: Rate 1-10
2. ISSUES: Any problems detected
3. RECOMMENDATIONS: 3 specific things to improve
4. PRIORITY: What to fix first

Be direct and actionable."""
    result = groq_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1500
    )
    if result.get("success"):
        return jsonify({"diagnosis": result["reply"], "model_used": result.get("model_used")})
    return jsonify({"error": result.get("error", "AI failed")}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
