# 🚀 Deploy Rahman Shorts — Vercel + Render (FREE)

**No AWS needed. No credit card required. Free forever.**

---

## 🎯 What We're Doing

| Part | Platform | Why |
|------|----------|-----|
| **Frontend** | Vercel | Free, instant, global CDN |
| **Backend** | Render | Free, supports Docker + FFmpeg |

**Total Cost: $0**

---

## 📋 Prerequisites

- GitHub account (free)
- Git installed on your computer

---

## PART 1: Deploy Backend to Render (5 minutes)

### Step 1: Push Code to GitHub

```bash
# 1. Create a new repo on GitHub (don't add README yet)
# Go to https://github.com/new → Name: rahman-shorts → Create

# 2. In your project folder, run:
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/rahman-shorts.git
git push -u origin main
```

### Step 2: Connect Render to GitHub

1. Go to **https://render.com** → Sign up with GitHub (free)
2. Click **"New +"** → **"Blueprint"**
3. Click **"Connect a repository"**
4. Select your `rahman-shorts` repo
5. Render will detect `render.yaml` automatically
6. Click **"Apply"**
7. Wait 5-10 minutes for build (Docker builds FFmpeg + Python)
8. Copy your backend URL: `https://rahman-shorts-api.onrender.com`

> **Note:** Render free tier spins down after 15 min of inactivity. First request after idle takes ~30 seconds to wake up. After that it's fast.

---

## PART 2: Deploy Frontend to Vercel (2 minutes)

### Step 1: Update API URL

Open `frontend/index.html` and find this line:

```javascript
return 'https://rahman-shorts-api.onrender.com'; // <-- CHANGE THIS AFTER RENDER DEPLOY
```

**Replace it with your actual Render URL:**

```javascript
return 'https://rahman-shorts-api.onrender.com'; // Your Render URL here
```

Save the file. Commit and push:

```bash
git add frontend/index.html
git commit -m "Update API URL"
git push
```

### Step 2: Deploy to Vercel

1. Go to **https://vercel.com** → Sign up with GitHub (free)
2. Click **"Add New Project"**
3. Select your `rahman-shorts` repo
4. **Framework Preset:** Other
5. **Root Directory:** `./frontend`
6. Click **"Deploy"**
7. Wait 30 seconds → Done!
8. Your frontend URL: `https://rahman-shorts.vercel.app`

---

## ✅ Test Everything

1. Open your Vercel URL: `https://rahman-shorts.vercel.app`
2. Paste a YouTube link
3. Click **Generate Shorts**
4. Wait for processing (Render backend wakes up if idle)
5. Download your viral shorts!

---

## 🔧 Optional: Add OpenAI API Key

For real AI transcription (instead of mock):

1. Go to **https://platform.openai.com/api-keys**
2. Create new key
3. In Render dashboard → Your Service → Environment
4. Add: `OPENAI_API_KEY` = `sk-...`
5. Save → Auto redeploys

---

## 🆘 Troubleshooting

| Problem | Fix |
|---------|-----|
| "Backend not connected" | Check API_BASE in frontend matches Render URL |
| "CORS error" | Backend CORS_ORIGINS is set to `*` — should work |
| Processing takes 2 min | Render free tier sleeps — first request is slow |
| "File too large" | Max 2GB on Render free tier |
| Video won't download | Check if clip actually generated — check Render logs |

---

## 💰 Cost

| Platform | Cost |
|----------|------|
| Vercel (Frontend) | **$0 forever** |
| Render (Backend) | **$0 forever** (sleeps after 15 min idle) |
| OpenAI API | **$0** if you don't add key (uses mock) |
| **Total** | **$0** |

---

## 🎉 You're Live!

- **Frontend:** `https://rahman-shorts.vercel.app`
- **Backend:** `https://rahman-shorts-api.onrender.com`
- **API Health:** `https://rahman-shorts-api.onrender.com/api/health`

Share your Vercel link with anyone — it works worldwide.
