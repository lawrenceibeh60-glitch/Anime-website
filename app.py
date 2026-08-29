from flask import Flask, render_template_string, jsonify, request, Response, stream_with_context
import requests
import os
import re
import subprocess
from bs4 import BeautifulSoup

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
    if not q: return jsonify({"results": anilist_trending(20)})
    try: return jsonify({"results": anilist_search(q, 20)})
    except Exception as e: return jsonify({"results": [], "error": str(e)})

@app.route("/api/anime/<int:anime_id>")
def anime_detail(anime_id):
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

if __name__ == "__main__": app.run(debug=True, host="0.0.0.0", port=5000)
