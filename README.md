\# 🎨 ExplainIT



\*\*Turns any topic into a short illustrated comic explainer — grounded in real source material, so it doesn't teach the wrong thing.\*\*



If the topic isn't covered by the active source document, it refuses to generate rather than making something up. That's the entire point of the project.



\---



\## 🧠 How It Works



Topic → 🔍 Retrieval (FAISS) → ✅ Grounding Check → ✍️ Panel Script (Gemini) → 🖼️ Illustration (Pollinations) → 📖 Comic Reader





1\. \*\*🔍 Retrieval\*\* — the topic is searched against a vector database built from one active source document

2\. \*\*✅ Grounding check\*\* — if nothing relevant enough is found, the system refuses to generate instead of guessing

3\. \*\*✍️ Panel script\*\* — an LLM turns the retrieved facts into a 3-panel script (caption + scene description per panel), using ONLY the retrieved content

4\. \*\*🖼️ Illustration\*\* — each scene description becomes an image

5\. \*\*📖 Comic reader\*\* — the frontend displays it as a page-through comic



\---



\## 📁 Project Structure



explainit/

├── backend/ 🐍 FastAPI + LangChain + FAISS

│ ├── main.py The API — /generate, /upload-source

│ ├── retriever.py Standalone script: builds the GAN vector store

│ ├── ingest.py Shared module: PDF/txt extraction + vector store building

│ ├── image\_generator.py Standalone test script for image generation

│ └── data/

│ ├── gan\_source.txt Default source document (GANs)

│ ├── faiss\_index/ The active vector store (regenerated, not permanent)

│ └── images/ Generated comic panel images

│

└── frontend/ ⚛️ Vite + React + Tailwind + Framer Motion

└── src/components/

├── Hero.jsx Landing page, topic input, upload, loading/error states

└── ComicReader.jsx The actual comic panel viewer





\---



\## 🚀 Running It



\*\*Backend\*\* — Terminal 1:

```bash

cd backend

venv\\Scripts\\activate

uvicorn main:app

```

Runs at `http://127.0.0.1:8000` ⚠️ Do NOT use `--reload` — it crashes on Windows due to how many files `transformers` installs.



\*\*Frontend\*\* — Terminal 2:

```bash

cd frontend

npm run dev

```

Runs at `http://localhost:5173`



\---



\## 🔑 Environment Setup



Create `backend/.env` — \*\*never commit this\*\*, it's already in `.gitignore`:



GOOGLE\_API\_KEY=your\_key\_here

HF\_TOKEN=your\_huggingface\_token\_here





Get a Google key at \[aistudio.google.com/apikey](https://aistudio.google.com/apikey). The HF token isn't strictly required anymore (image generation runs through Pollinations.ai, not Hugging Face) but `sentence-transformers` embeddings still use it for higher rate limits.



\---



\## ⚠️ Important: Single Active Document



There is only \*\*ONE\*\* active source document at a time, not a growing library. Uploading a new file (via the UI or `POST /upload-source`) \*\*overwrites\*\* `data/faiss\_index`, replacing whatever was grounded before it.



To restore GAN grounding after testing an upload:

```bash

cd backend

python retriever.py

```



\---



\## 🔌 API Endpoints



| Endpoint | Method | Description |

|---|---|---|

| `/generate` | POST | Body `{"topic": "..."}` → returns panels + image URLs, or `{"grounded": false, "message": "..."}` if not covered |

| `/upload-source` | POST | Multipart file upload (`.txt` or `.pdf`) — replaces the active source document |



\---



\## 🐛 Known Issues / Things To Know



\- ⚠️ `STYLE\_SUFFIX` (the image style prompt) is duplicated in both `main.py` and `image\_generator.py` — if you change the art style, update both or they'll drift out of sync

\- ⚠️ `GROUNDING\_THRESHOLD` in `main.py` is tuned for the current embedding model — if you swap embedding models, re-test with a known-good and known-bad topic before trusting it

\- ⚠️ CORS in `main.py` is locked to `http://localhost:5173` — if you ever run the frontend on a different port, update `allow\_origins` or requests will silently fail

\- ✅ Image generation runs through \*\*Pollinations.ai\*\* (free, no API key, no rate limit hit so far) — Hugging Face's free tier and Gemini's free image tier were both tried first and hit account-level blocks; Pollinations was the one that actually worked reliably



\---



<p align="center">Built for Generative AI, Sem-IX 🎓</p>

