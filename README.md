# KYRO ANIME — Render Deployment Package

## What This Package Contains

This is your hardened backend adapted for Render.com deployment.

| File | Purpose |
|------|---------|
| `app.py` | Hardened Flask backend (62KB) — same security, Render-compatible |
| `requirements.txt` | Python dependencies for Render |
| `runtime.txt` | Python 3.11 version pin |
| `render.yaml` | Blueprint for one-click Render deploy |
| `.env.example` | Environment variable template |
| `.gitignore` | Prevents committing secrets |
| `RENDER_DEPLOY.md` | Full deployment walkthrough |

## Integrating With Your Existing Files

You mentioned you have other files. Here's how they fit:

### Your Existing Files → Where They Go

```
kyro-render/
├── app.py                    # ← THIS PACKAGE (replaces your old app.py)
├── requirements.txt          # ← THIS PACKAGE
├── runtime.txt               # ← THIS PACKAGE
├── render.yaml               # ← THIS PACKAGE
├── .env.example              # ← THIS PACKAGE
├── .gitignore                # ← THIS PACKAGE
├── RENDER_DEPLOY.md          # ← THIS PACKAGE
│
├── index.html                # ← YOUR EXISTING FILE (homepage)
├── auth.html                 # ← YOUR EXISTING FILE (auth page)
├── admin.html                # ← YOUR EXISTING FILE (admin panel)
├── premium.html              # ← YOUR EXISTING FILE (premium page)
│
└── templates/
    ├── index.html            # ← OR your existing templates/index.html
    ├── dashboard.html        # ← YOUR EXISTING FILE (admin dashboard)
    └── (other templates)     # ← YOUR EXISTING FILES
```

### Important: app.py Changes

The new `app.py` in this package **replaces your old app.py completely**.

It keeps ALL your routes:
- `/` → index page
- `/api/chat` → AI chat
- `/api/search` → anime search
- `/api/stream/<ep_hash>` → video streaming
- `/api/download` → downloads
- `/admin/*` → all admin endpoints
- `/admin/dashboard` → admin dashboard
- `/admin/logs` → visitor logs

Plus adds military-grade security:
- Argon2id password hashing
- Rate limiting on every endpoint
- WAF patterns (SQLi, XSS, path traversal blocking)
- HMAC-signed audit logs
- Session IP/UA binding
- Input sanitization
- Security headers (CSP, HSTS, COEP, COOP)

### What You Need to Do

1. **Copy this package** into your project folder
2. **Copy your existing HTML files** into the same folder (or `templates/`)
3. **Copy your existing CSS/JS/assets** into `static/`
4. **Set environment variables** in Render dashboard
5. **Deploy**

### Frontend Changes Needed

Your frontend code should work as-is, but update these API calls:

**Before (old app.py):**
```javascript
fetch("/api/password/check", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ password: pwd })
})
```

**After (new app.py) — same, but response now includes session_token:**
```javascript
fetch("/api/password/check", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ password: pwd })
})
.then(r => r.json())
.then(data => {
  if (data.success) {
    localStorage.setItem("kyro_session", data.session_token);
    // New: session_token is returned for enhanced security
  }
})
```

**Admin API calls now need the session token too:**
```javascript
fetch("/admin/api/status", {
  headers: {
    "X-Admin-Key": ownerKey,
    "X-Session-Token": localStorage.getItem("kyro_session") || ""
  }
})
```

## Quick Start

```bash
# 1. Merge this package with your existing files
cp -r kyro-render/* ~/my-kyro-project/
cd ~/my-kyro-project

# 2. Add your existing frontend files if not already there
# (index.html, auth.html, admin.html, premium.html, templates/dashboard.html)

# 3. Set up environment
cp .env.example .env
# Edit .env with your secrets

# 4. Test locally
pip install -r requirements.txt
gunicorn app:app

# 5. Deploy to Render
git add .
git commit -m "Kyro Security V1.0 Render"
git push origin main
# Then connect repo on Render dashboard
```

## Questions?

If something breaks, check:
1. `RENDER_DEPLOY.md` for troubleshooting
2. Render Logs tab for error messages
3. Your `.env` variables are all set correctly
