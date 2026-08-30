# KYRO ANIME — Render.com Deployment Guide

## Prerequisites
- GitHub account
- Render account (free tier works)
- Your existing frontend files (index.html, auth.html, etc.)

## Step 1: Prepare Your Repo

```bash
# 1. Unzip this package into your project folder
unzip kyro-render.zip

# 2. Add your existing frontend files
# Place these in the same folder as app.py:
# - index.html (or templates/index.html)
# - auth.html
# - admin.html
# - premium.html
# - dashboard.html (in templates/)
# - Any other HTML/CSS/JS files

# 3. Create .env from template (DO NOT commit this)
cp .env.example .env
# Edit .env with your real secrets

# 4. Commit and push to GitHub
git init
git add .
git commit -m "Kyro Security V1.0 - Render deployment"
git push origin main
```

## Step 2: Deploy on Render

1. Go to [render.com](https://render.com) and sign in
2. Click **New +** → **Web Service**
3. Connect your GitHub repo
4. Configure:
   - **Name:** `kyro-anime` (or your choice)
   - **Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Plan:** Free (or Starter $7/mo for no cold starts)
5. Click **Advanced** → add environment variables from `.env`
6. Click **Create Web Service**

## Step 3: Set Environment Variables

In the Render Dashboard, go to your service → **Environment** tab:

| Variable | Value | Notes |
|----------|-------|-------|
| `FLASK_SECRET_KEY` | `openssl rand -hex 64` | Generate locally |
| `KYRO_PASSWORD` | Your site password | Min 12 chars |
| `GROQ_API_KEY` | Your Groq API key | Get at groq.com |
| `AI_ERROR_KEY` | Same as GROQ or separate | For AI error analysis |
| `KYRO_OWNER_KEY` | `openssl rand -hex 64` | Admin access |
| `KYRO_STAFF_KEY` | `openssl rand -hex 64` | Staff access |
| `KYRO_ALLOWED_ORIGINS` | `https://yourapp.onrender.com` | Your actual URL |

## Step 4: Verify Deployment

```bash
# Check if app is live
curl https://yourapp.onrender.com/api/status

# Test security headers
curl -I https://yourapp.onrender.com

# Test rate limiting (should get 429 after 5 failed logins)
for i in {1..6}; do curl -X POST https://yourapp.onrender.com/api/password/check -H "Content-Type: application/json" -d '{"password":"wrong"}'; echo; done
```

## Render-Specific Notes

### What Render Handles Automatically
- **TLS/HTTPS** — Render terminates SSL, no cert needed
- **DDoS protection** — Basic layer included
- **Static IP** — Your `.onrender.com` URL
- **Auto-deploy** — Push to GitHub = auto redeploy

### What the App Still Handles
- Argon2id password hashing
- Rate limiting (per-instance, memory-based)
- WAF patterns (SQLi, XSS, path traversal)
- Input sanitization
- Session security
- Audit logging
- Admin role-based access

### Free Tier Limitations
- **Cold starts:** 15 min idle = spin down, ~60s wake-up
- **Ephemeral filesystem:** `/tmp` persists during runtime only
- **Logs:** Check Render dashboard → Logs tab
- **No custom domains** on free (use `.onrender.com`)

### Upgrading
- **Starter ($7/mo):** No cold starts, always-on
- **Custom domain:** Add in dashboard, point DNS CNAME to Render

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails | Check `requirements.txt` has all deps |
| App crashes | Check Logs tab for traceback |
| 502 Bad Gateway | Gunicorn crashed, check `app:app` entry point |
| CORS errors | Update `KYRO_ALLOWED_ORIGINS` with your URL |
| Admin 403 | Generate new keys, set in env vars |

## Security on Render

Render handles the perimeter (TLS, basic DDoS). Your app handles:
- Application-layer security (WAF, rate limiting, input validation)
- Authentication (Argon2id, session binding)
- Authorization (role-based admin keys)
- Audit (security event logging to `/tmp/kyro_security.json`)

**Note:** Security logs are ephemeral on free tier. For persistent logging, add a logging service or upgrade.
