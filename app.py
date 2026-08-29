from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context
import requests
import os
import re
import subprocess
from bs4 import BeautifulSoup
from datetime import datetime
from user_agents import parse as ua_parse
import json

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
            "screen_size": request.headers.get('Viewport-Width', 'unknown'),
            "action": action,
            "details": details,
            "path": request.path,
            "referrer": request.headers.get('Referer', 'direct')
        }

        # Append to log file
        logs = []
        if os.path.exists(VISITOR_LOG):
            try:
                with open(VISITOR_LOG, 'r') as f:
                    logs = json.load(f)
            except: pass

        logs.append(entry)
        # Keep last 5000 entries
        logs = logs[-5000:]

        with open(VISITOR_LOG, 'w') as f:
            json.dump(logs, f, indent=2)

    except Exception as e:
        print(f"[KYRO LOG ERROR] {e}")

# =====


app = Flask(__name__)

# ===== FFMPEG STATUS CHECK (runs on startup) =====
FFMPEG_AVAILABLE = False
try:
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        FFMPEG_AVAILABLE = True
        print(f"[KYRO] FFMPEG IS AVAILABLE: {result.stdout.splitlines()[0]}")
    else:
        print("[KYRO] FFMPEG NOT FOUND - quality transcoding disabled")
except Exception as e:
    print(f"[KYRO] FFMPEG CHECK FAILED: {e}")
    print("[KYRO] Quality transcoding will NOT work. Downloads = original quality only.")
# ==================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ANILIST_URL = "https://graphql.anilist.co"
ANIMEHEAVEN = "https://animeheaven.me"

SYSTEM_PROMPT = """You are KYRO, an AI anime expert. You help users find, watch, and download anime.
Be friendly, use anime knowledge, and suggest specific titles."""

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
            text = a.get_text(strip=True)
            if "gate.php" in href and "gatea" in onclick:
                match = re.search(r'gatea\("([^"]+)"\)', onclick)
                if match:
                    ep_hash = match.group(1)
                    # Extract episode number from nested divs
                    watch2 = a.find("div", class_=lambda x: x and "watch2" in str(x))
                    if watch2:
                        ep_num = watch2.get_text(strip=True)
                    else:
                        ep_num = re.match(r"(\d+)", text.replace("Episode", "").strip())
                        ep_num = ep_num.group(1) if ep_num else "0"
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
        "ffmpeg": "available" if FFMPEG_AVAILABLE else "not_installed",
        "quality_transcoding": "enabled" if FFMPEG_AVAILABLE else "disabled"
    })

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("messages", [{}])[-1].get("content", "") if data.get("messages") else ""
    log_visitor(request, "chat", f"Chat message: {msg[:50]}...")
    messages = data.get("messages", [])
    if not GROQ_API_KEY: return jsonify({"reply": "Set your GROQ_API_KEY environment variable to enable AI chat."})
    payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages, "temperature": 0.8, "max_tokens": 1024}
    try:
        r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json=payload, timeout=30)
        result = r.json()
        if "choices" in result and len(result["choices"]) > 0:
            return jsonify({"reply": result["choices"][0]["message"]["content"]})
        elif "error" in result:
            return jsonify({"reply": f"Groq API Error: {result['error'].get('message', 'Unknown error')}"})
        else:
            return jsonify({"reply": "Unexpected response from AI. Please try again."})
    except Exception as e: return jsonify({"reply": f"Connection error: {str(e)}. Check your API key and try again."})

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
    filename = request.args.get("filename", "episode.mp4")
    quality = request.args.get("quality", "original")  # original, 720p, 480p, 360p
    if not url: return jsonify({"error": "No URL"}), 400
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://animeheaven.me/gate.php"}
        
        # If quality is original, just proxy the download
        if quality == "original" or quality not in ["720p", "480p", "360p"]:
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
        
        # For transcoded quality, check if ffmpeg is available
        if not FFMPEG_AVAILABLE:
            print(f"[KYRO] FFMPEG NOT AVAILABLE - returning original quality for {filename}")
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
        
        # ffmpeg is available - try transcoding
        print(f"[KYRO] Starting ffmpeg transcode: {filename} -> {quality}")
        scale_map = {"720p": "1280:720", "480p": "854:480", "360p": "640:360"}
        scale = scale_map.get(quality, "1280:720")
        
        # Use /tmp for temp files (Render allows this)
        temp_dir = "/tmp/kyro_" + str(os.getpid())
        os.makedirs(temp_dir, exist_ok=True)
        temp_input = os.path.join(temp_dir, "input.mp4")
        temp_output = os.path.join(temp_dir, f"out_{quality}.mp4")
        
        try:
            # Download input (with size limit check)
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            total_size = 0
            max_size = 500 * 1024 * 1024  # 500MB limit for free tier
            with open(temp_input, "wb") as f:
                for chunk in r.iter_content(chunk_size=262144):
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise Exception("Video too large for free tier transcoding (limit: 500MB)")
                    f.write(chunk)
            
            print(f"[KYRO] Downloaded {total_size/1024/1024:.1f}MB, starting ffmpeg...")
            
            # Transcode with ffmpeg
            cmd = [
                "ffmpeg", "-y", "-i", temp_input,
                "-vf", f"scale={scale}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                temp_output
            ]
            result = sp.run(cmd, capture_output=True, timeout=120)
            
            if result.returncode != 0:
                print(f"[KYRO] ffmpeg failed: {result.stderr.decode()[:200]}")
                raise Exception("ffmpeg transcoding failed")
            
            # Check output file exists and has size
            if not os.path.exists(temp_output) or os.path.getsize(temp_output) < 1024:
                raise Exception("ffmpeg output file is empty")
            
            out_size = os.path.getsize(temp_output)
            print(f"[KYRO] Transcode complete: {out_size/1024/1024:.1f}MB")
            
            # Return transcoded file
            def generate():
                with open(temp_output, "rb") as f:
                    while True:
                        chunk = f.read(262144)
                        if not chunk: break
                        yield chunk
                # Cleanup
                try:
                    os.remove(temp_input)
                    os.remove(temp_output)
                    os.rmdir(temp_dir)
                except: pass
            
            return Response(generate(), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename.replace('.mp4', f'_{quality}.mp4')}"})
            
        except Exception as transcode_err:
            print(f"[KYRO] Transcode failed: {transcode_err}")
            # Cleanup on failure
            try:
                if os.path.exists(temp_input): os.remove(temp_input)
                if os.path.exists(temp_output): os.remove(temp_output)
                if os.path.exists(temp_dir): os.rmdir(temp_dir)
            except: pass
            # Fall back to original quality
            print(f"[KYRO] Falling back to original quality for {filename}")
            r = requests.get(url, headers=headers, stream=True, timeout=60)
            return Response(stream_with_context(r.iter_content(chunk_size=262144)), content_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={filename}", "Content-Length": r.headers.get("Content-Length", "")})
        
    except Exception as e: 
        return jsonify({"error": str(e)}), 500



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
        .mobile{color:#ef5350}
        .pc{color:#00d26a}
        .count{position:fixed;top:20px;right:20px;background:#2962ff;padding:10px 20px;border-radius:8px;font-weight:bold}
        </style></head><body>
        <h1>🕵️ KYRO Visitor Logs</h1>
        <div class="count">Total Visits: """ + str(len(logs)) + """</div>
        <table>
        <tr><th>Time</th><th>IP</th><th>Device</th><th>OS</th><th>Browser</th><th>Type</th><th>Action</th><th>Details</th></tr>"""

        for entry in reversed(logs[-200:]):  # Show last 200
            device_type = "📱" if entry.get('is_mobile') else "💻" if entry.get('is_pc') else "📱" if entry.get('is_tablet') else "❓"
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
    """Return logs as JSON for external viewers"""
    try:
        if not os.path.exists(VISITOR_LOG):
            return jsonify({"visits": [], "total": 0})
        with open(VISITOR_LOG, 'r') as f:
            logs = json.load(f)
        return jsonify({"visits": logs, "total": len(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__": app.run(debug=True, host="0.0.0.0", port=5000)
