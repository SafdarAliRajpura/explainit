# 🎨 ExplainIT

**Turns any topic into a short illustrated comic explainer — grounded in real source material, so it doesn't teach the wrong thing.**

If the topic isn't covered by the active source document, it refuses to generate rather than making something up. That's the entire point of the project.

---

## 🧠 How It Works

Topic → 🔍 Retrieval (FAISS) → ✅ Grounding Check → ✍️ Panel Script (Gemini) → 🖼️ Illustration (Pollinations) → 📖 Comic Reader


1. **🔍 Retrieval** — the topic is searched against a vector database built from one active source document
2. **✅ Grounding check** — if nothing relevant enough is found, the system refuses to generate instead of guessing
3. **✍️ Panel script** — an LLM turns the retrieved facts into a 3-panel script (caption + scene description per panel), using ONLY the retrieved content
4. **🖼️ Illustration** — each scene description becomes an image
5. **📖 Comic reader** — the frontend displays it as a page-through comic
6. **🔗 Share** — any generated panel can be posted directly to LinkedIn, real account, real post

---

## 📁 Project Structure

explainit/
├── backend/ 🐍 FastAPI + LangChain + FAISS
│ ├── main.py The API — /generate, /upload-source, /auth/linkedin/*, /linkedin/post-panel
│ ├── retriever.py Standalone script: builds the GAN vector store
│ ├── ingest.py Shared module: PDF/txt extraction + vector store building
│ ├── image_generator.py Standalone test script for image generation
│ └── data/
│ ├── gan_source.txt Default source document (GANs)
│ ├── faiss_index/ The active vector store (regenerated, not permanent)
│ └── images/ Generated comic panel images
│
└── frontend/ ⚛️ Vite + React + Tailwind + Framer Motion
└── src/components/
├── Hero.jsx Landing page, topic input, upload, loading/error states
└── ComicReader.jsx The actual comic panel viewer


---

## 🚀 Running It

**Backend** — Terminal 1:
```bash
cd backend
venv\Scripts\activate
uvicorn main:app
```
Runs at `http://127.0.0.1:8000` ⚠️ Do NOT use `--reload` — it crashes on Windows due to how many files `transformers` installs.

**Frontend** — Terminal 2:
```bash
cd frontend
npm run dev
```
Runs at `http://localhost:5173`

---

## 🔑 Environment Setup

Create `backend/.env` — **never commit this**, it's already in `.gitignore`:

GOOGLE_API_KEY=your_key_here
HF_TOKEN=your_huggingface_token_here
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret


- Google key → [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- HF token isn't strictly required anymore (image generation runs through Pollinations.ai, not Hugging Face) but `sentence-transformers` embeddings still use it for higher rate limits
- LinkedIn keys → create an app at [developer.linkedin.com](https://developer.linkedin.com), attach it to a LinkedIn Page, and enable both **"Sign In with LinkedIn using OpenID Connect"** and **"Share on LinkedIn"** under the Products tab. Add `http://localhost:8000/auth/linkedin/callback` as an authorized redirect URL.

---

## ⚠️ Important: Single Active Document

There is only **ONE** active source document at a time, not a growing library. Uploading a new file (via the UI or `POST /upload-source`) **overwrites** `data/faiss_index`, replacing whatever was grounded before it.

To restore GAN grounding after testing an upload:
```bash
cd backend
python retriever.py
```

---

## 🔗 LinkedIn Integration

Lets a user connect their real LinkedIn account and publish any generated comic panel as a real post.

**Flow:** `/auth/linkedin/login` → user logs into LinkedIn directly (never through this app) → LinkedIn redirects back to `/auth/linkedin/callback` with an access token and identity → `/linkedin/post-panel` uploads the chosen panel's image to LinkedIn and publishes it with a caption.

⚠️ **The session is stored in memory only** (`linkedin_session` dict in `main.py`), not in a database. This means:
- Every time the backend server restarts, you must log in again via `/auth/linkedin/login` before posting will work
- This is intentional for a single-user demo — it is **not** built to support multiple simultaneous users

⚠️ **Posting is real and permanent.** There is no "test mode" — hitting `/linkedin/post-panel` publishes an actual public post to the connected LinkedIn account. Treat it accordingly during demos.

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/generate` | POST | Body `{"topic": "..."}` → returns panels + image URLs, or `{"grounded": false, "message": "..."}` if not covered |
| `/upload-source` | POST | Multipart file upload (`.txt` or `.pdf`) — replaces the active source document |
| `/auth/linkedin/login` | GET | Redirects to LinkedIn's login/consent screen |
| `/auth/linkedin/callback` | GET | LinkedIn redirects here after login — exchanges code for token, fetches identity |
| `/linkedin/post-panel` | POST | Query params `panel_number` + `caption` → uploads that panel's image and publishes a real LinkedIn post |

---

## 🐛 Known Issues / Things To Know

- ⚠️ `STYLE_SUFFIX` (the image style prompt) is duplicated in both `main.py` and `image_generator.py` — if you change the art style, update both or they'll drift out of sync
- ⚠️ `GROUNDING_THRESHOLD` in `main.py` is tuned for the current embedding model — if you swap embedding models, re-test with a known-good and known-bad topic before trusting it
- ⚠️ CORS in `main.py` is locked to `http://localhost:5173` — if you ever run the frontend on a different port, update `allow_origins` or requests will silently fail
- ⚠️ LinkedIn session is in-memory — resets on every backend restart, requiring re-login
- ✅ Image generation runs through **Pollinations.ai** (free, no API key, no rate limit hit so far) — Hugging Face's free tier and Gemini's free image tier were both tried first and hit account-level blocks; Pollinations was the one that actually worked reliably
- ✅ LinkedIn's posting permission (`w_member_social`) is part of the self-serve tier — no lengthy approval wait, unlike LinkedIn's Marketing/Partner API products

---

<p align="center">Built for Generative AI, Sem-IX 🎓</p>