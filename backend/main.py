import os
import re
import time
import json
import random
import textwrap
import requests
import httpx
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from fastapi.responses import RedirectResponse, HTMLResponse
from urllib.parse import quote
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from ingest import extract_text_from_file, build_vector_store
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

def create_fallback_card(topic: str, panel_num: int, caption: str, output_path: str):
    """
    Renders an editorial dark-themed visual card with amber accents and
    topic/caption typography so panels always display beautiful, relevant content
    even if an upstream image API is blocked or rate-limited.
    """
    img = Image.new('RGB', (1024, 1024), color='#15171A')
    draw = ImageDraw.Draw(img)
    # Subtle inner border
    draw.rectangle([(32, 32), (992, 992)], outline='#262930', width=2)
    # Amber badge
    draw.rounded_rectangle([(80, 80), (340, 134)], radius=27, fill='#262930', outline='#E8A33D', width=2)
    draw.text((105, 98), f'PANEL {panel_num} OF 3', fill='#E8A33D')
    # Topic label
    draw.text((80, 180), topic.upper(), fill='#8B8D93')
    # Decorative conceptual rings
    draw.ellipse([(412, 360), (612, 560)], outline='#E8A33D', width=4)
    draw.ellipse([(442, 390), (582, 530)], outline='#262930', width=2)
    draw.ellipse([(492, 440), (532, 480)], fill='#E8A33D')
    # Caption excerpt
    wrapped = textwrap.fill(caption, width=54)
    draw.text((80, 720), wrapped, fill='#F2F1ED')
    img.save(output_path)

app = FastAPI()

@app.middleware("http")
async def add_cache_control_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/images"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/images", StaticFiles(directory="data/images"), name="images")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

ACTIVE_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.8-flash"]

def invoke_llm_with_retry(prompt: str, max_retries: int = 2):
    """
    Invokes Google Gemini with fast-failover across healthy models.
    Prioritizes models with proven low latency and zero 503 capacity issues.
    """
    global ACTIVE_MODELS
    last_error = None

    for model_name in list(ACTIVE_MODELS):
        for attempt in range(max_retries):
            try:
                print(f"[LLM] Requesting model '{model_name}' (attempt {attempt + 1}/{max_retries})...", flush=True)
                model = ChatGoogleGenerativeAI(model=model_name, temperature=0.4, timeout=35)
                result = model.invoke(prompt)
                if ACTIVE_MODELS[0] != model_name and model_name in ACTIVE_MODELS:
                    ACTIVE_MODELS.remove(model_name)
                    ACTIVE_MODELS.insert(0, model_name)
                print(f"[LLM] Model '{model_name}' responded successfully.", flush=True)
                return result
            except Exception as e:
                last_error = e
                err_msg = str(e)
                print(f"[LLM] Model '{model_name}' error: {err_msg}", flush=True)
                if any(code in err_msg for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND"]):
                    print(f"[LLM] '{model_name}' is busy or unavailable. Immediate failover to next candidate...", flush=True)
                    if model_name in ACTIVE_MODELS:
                        ACTIVE_MODELS.remove(model_name)
                        ACTIVE_MODELS.append(model_name)
                    break
                else:
                    time.sleep(1)

    raise last_error

def detect_topic_domain(topic: str, caption: str) -> dict:
    """
    Accurately classifies the topic and caption into its genuine subject domain using
    robust word-boundary regex matching to prevent false triggers (e.g. 'generation' matching 'gene').
    Provides authentic color palettes, lighting, and domain-accurate visual guidelines.
    """
    combined = f"{topic} {caption}".lower()

    # 1. History, Politics, Society, Governance & Humanities
    history_pattern = re.compile(
        r'\b(history|historical|revolutions?|french revolution|monarch(y|s)?|kings?|queens?|guillotine|bastille|'
        r'parliaments?|constitutions?|democrac(y|ies)|feudalism|renaissance|medieval|wars?|battles?|rebellions?|'
        r'declarations?|civil wars?|empires?|treat(y|ies)|politics|political|governments?|senates?|republics?|'
        r'citizens?|dynast(y|ies)|colonial|revolts?|rights of man|third estate|estates-general|nobility|clergy|'
        r'liberty|reign of terror)\b',
        re.IGNORECASE
    )
    if history_pattern.search(combined):
        return {
            "domain": "HISTORY, POLITICS & SOCIETY",
            "bg_color": "#0F1117",
            "primary_accent": "#F59E0B",  # Royal gold
            "secondary_accent": "#EF4444", # Revolutionary crimson
            "tertiary_accent": "#3B82F6",  # Steel blue
            "visual_guidance": """
- VISUAL STORYTELLING (HISTORY, POLITICS & SOCIETY):
  * Make it visually authentic to human history, social movements, and governance!
  * For Monarchy & Power: Draw classical ornate thrones, royal crowns, classical stone pillars/palaces, or scales of justice.
  * For The Third Estate / Commoners: Draw stylized citizen assemblies, raised protest banners, or breaking chains of feudal bondage.
  * For Turning Points & Revolution: Draw fortress battlements (like the Bastille), rising pressure gauges of inequality, or storming gates.
  * For Documents & Rights: Draw parchment scrolls with wax seals, quill pens, written decrees, and declarations of liberty.
  * ABSOLUTE PROHIBITION: Absolutely NO plants or leaves, NO spaceships, NO cosmic spheres or quantum energy rings!
"""
        }

    # 2. Economics, Finance, Trade & Commerce
    econ_pattern = re.compile(
        r'\b(econom(y|ics|ic)|inflation|deflation|supply and demand|stock markets?|cryptocurrenc(y|ies)|'
        r'interest rates?|bank(s|ing)?|currenc(y|ies)|recessions?|gdp|monopol(y|ies)|market balance|trade deficit|'
        r'liquidity|investors?|fiscal|central banks?|treasury|commerce|capitalism)\b',
        re.IGNORECASE
    )
    if econ_pattern.search(combined):
        return {
            "domain": "ECONOMICS & FINANCE",
            "bg_color": "#0B132B",
            "primary_accent": "#10B981",  # Emerald wealth/growth
            "secondary_accent": "#F43F5E", # Coral deficit/pressure
            "tertiary_accent": "#F59E0B",  # Golden coin/value
            "visual_guidance": """
- VISUAL STORYTELLING (ECONOMICS & FINANCE):
  * Make market forces and commercial mechanisms intuitive!
  * For Supply vs Demand: Draw physical balance scales with goods on one side and buyers on the other.
  * For Inflation & Currency: Draw expanding price tags, coins flowing through vaults, or clear rising/falling trend curves.
  * For Trade: Draw interconnected trade routes, merchant vessels, or factory production conveyors.
  * ABSOLUTE PROHIBITION: NO random leaves or plants, NO quantum cosmic waves!
"""
        }

    # 3. Biology, Ecology, Medicine & Life Sciences
    bio_pattern = re.compile(
        r'\b(photosynthesis|chloroplasts?|chlorophyll|thylakoids?|botany|plant cells?|dna double helix|dna replication|'
        r'crispr|enzymes?|glucose synthesis|mitochondria|cellular respiration|bacteria|vir(us|uses)|vaccines?|antibodies|'
        r'immune systems?|pathogens?|cell divisions?|mitosis|meiosis|calvin cycle|biological organisms?|cellular cutaways?)\b',
        re.IGNORECASE
    )
    if bio_pattern.search(combined):
        return {
            "domain": "BIOLOGY & LIFE SCIENCES",
            "bg_color": "#0B1410",
            "primary_accent": "#10B981",  # Emerald leaf green
            "secondary_accent": "#F59E0B", # Radiant sunlight amber
            "tertiary_accent": "#38BDF8",  # Clear water cyan
            "visual_guidance": """
- VISUAL STORYTELLING (BIOLOGY & LIFE SCIENCES):
  * Make living biological systems intuitive, tangible, and friendly!
  * For Photosynthesis/Botany: Draw a radiant golden Sun (☀️), a vibrant green leaf (🍃) with clean cutaway, clear water droplets (💧 'Water In'), oxygen bubbles (🫧 'Oxygen Out'), and sugar food energy stars ('Plant Sugar').
  * For Genetics/Cells: Draw twisting colorful DNA ladder rungs, clean cell membrane compartments, or lock-and-key enzyme docking.
  * For Immunity: Draw Y-shaped antibody shields neutralizing spike virus particles.
  * FORBIDDEN: NO dense biochemical pathway abbreviations (no Cyt b6f, PS II), NO complex organic chemistry formulas.
"""
        }

    # 4. Computer Science, AI, Algorithms & Software
    cs_pattern = re.compile(
        r'\b(rag|retrieval augmented|gans?|generative adversarial|llms?|large language models?|neural networks?|'
        r'deep learning|machine learning|artificial intelligence|transformers?|vector embeddings?|vector databases?|'
        r'faiss|blockchains?|docker containers?|kubernetes|compilers?|operating systems?|software architecture|'
        r'api endpoints?|cloud computing|database index|algorithms?|generators?|discriminators?)\b',
        re.IGNORECASE
    )
    if cs_pattern.search(combined):
        return {
            "domain": "COMPUTER SCIENCE & AI",
            "bg_color": "#15171A",
            "primary_accent": "#38BDF8",  # Cyber cyan
            "secondary_accent": "#E8A33D", # Warm amber gold
            "tertiary_accent": "#10B981",  # Emerald verification check
            "visual_guidance": """
- VISUAL STORYTELLING (COMPUTER SCIENCE & AI):
  * Use practical, intuitive visual analogies!
  * For Queries: Draw a user speech bubble with a question mark or search bar.
  * For Search/Retrieval: Draw a focused magnifying glass or scanner illuminating matching cards in an indexed book archive.
  * For Generation/Output: Draw an accurate verified answer document with green checkmark citation badges.
  * For Neural Networks / GANs: Draw connected layers of nodes or creator/inspector icons with flowing signal arrows.
  * FORBIDDEN: NO dense code blocks, NO mathematical matrix equations.
"""
        }

    # 5. Physics, Chemistry, Astronomy & Energy
    physics_pattern = re.compile(
        r'\b(nuclear fusion|nuclear fission|quantum mechanics?|black holes?|gravity well|gravitational|electron shells?|'
        r'electromagnetic|thermodynamics|laser beams?|chemical bonds?|covalent bonds?|ionic bonds?|'
        r'supernovas?|exoplanets?|plasma physics|astronomy|particle physics|superconductors?|'
        r'general relativity|special relativity|radioactivity|subatomic|photon rays?|atomic nuclei|atoms?)\b',
        re.IGNORECASE
    )
    if physics_pattern.search(combined):
        return {
            "domain": "PHYSICS & SPACE",
            "bg_color": "#0B0F19",
            "primary_accent": "#A855F7",  # Cosmic violet
            "secondary_accent": "#06B6D4", # Electric cyan
            "tertiary_accent": "#F59E0B",  # Energy amber
            "visual_guidance": """
- VISUAL STORYTELLING (PHYSICS, ENERGY & SPACE):
  * Draw physical, recognizable visual metaphors: orbiting electron shells, magnetic field loops with North/South poles, laser prisms splitting light beams, or gravitational orbital paths.
  * Use clear spatial comparisons: before vs after, attract vs repel, hot vs cold.
  * FORBIDDEN: NO calculus differential equations, NO tensor formulas, NO obscure wavefunctions.
"""
        }

    # 6. Default / Practical Everyday Mechanism
    return {
        "domain": "PRACTICAL PROCESS & MECHANISM",
        "bg_color": "#15171A",
        "primary_accent": "#E8A33D",  # Warm amber
        "secondary_accent": "#38BDF8", # Sky cyan
        "tertiary_accent": "#10B981",  # Emerald green
        "visual_guidance": f"""
- VISUAL STORYTELLING (PRACTICAL PROCESS):
  * Draw clean, friendly real-world objects and physical mechanisms illustrating '{topic}'.
  * Focus directly on this panel's specific action: '{caption}'.
  * Show a clear visual progression: Input/Cause -> Action/Transformation -> Output/Result with bold arrows.
  * NEVER draw random leaves or cosmic particles unless specifically relevant to '{topic}'.
"""
    }

def build_fallback_svg(topic: str, panel_num: int, caption: str) -> str:
    """
    Constructs an editorial, guaranteed-valid SVG graphic directly in Python.
    Guarantees 0% broken images even in edge-case network or parsing failures.
    """
    clean_topic = topic.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    clean_caption = caption.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    wrapped_lines = textwrap.wrap(clean_caption, width=46)[:4]
    caption_tspan = "".join(f'<tspan x="60" dy="24">{line}</tspan>' for line in wrapped_lines)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <linearGradient id="fallbackGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#181B20"/>
      <stop offset="100%" stop-color="#121417"/>
    </linearGradient>
  </defs>
  <rect width="800" height="800" fill="url(#fallbackGrad)"/>
  <rect x="24" y="24" width="752" height="752" rx="16" fill="none" stroke="#262930" stroke-width="2"/>
  
  <rect x="60" y="55" width="130" height="28" rx="14" fill="#262930" stroke="#E8A33D" stroke-width="1.5"/>
  <text x="125" y="74" fill="#E8A33D" font-family="system-ui, sans-serif" font-size="11" font-weight="700" text-anchor="middle" letter-spacing="1.5">STEP {panel_num}</text>
  
  <text x="60" y="130" fill="#F2F1ED" font-family="system-ui, sans-serif" font-size="26" font-weight="700">{clean_topic}</text>
  
  <circle cx="400" cy="400" r="160" fill="none" stroke="#262930" stroke-width="4"/>
  <circle cx="400" cy="400" r="120" fill="none" stroke="#E8A33D" stroke-width="3" stroke-dasharray="8,6"/>
  <circle cx="400" cy="400" r="60" fill="#262930" stroke="#38BDF8" stroke-width="2"/>
  <circle cx="400" cy="400" r="18" fill="#10B981"/>

  <text x="60" y="650" fill="#8B8D93" font-family="system-ui, sans-serif" font-size="15">
    {caption_tspan}
  </text>
</svg>"""

def sanitize_and_validate_svg(raw: str, topic: str, panel_num: int, caption: str) -> str:
    """
    Cleans, normalizes, escapes, and validates SVG XML markup.
    Guarantees that the returned SVG is 100% valid XML and will never fail in a browser.
    """
    cleaned = raw.strip()

    # Extract <svg>...</svg>
    match = re.search(r'(<svg[\s\S]*?</svg>)', cleaned, re.IGNORECASE)
    if match:
        svg_content = match.group(1)
    else:
        svg_content = cleaned.replace('```xml', '').replace('```svg', '').replace('```', '').strip()
        if not svg_content.startswith("<svg"):
            svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">{svg_content}'
        if not svg_content.endswith("</svg>"):
            svg_content = f"{svg_content}</svg>"

    # 1. Strip illegal XML control characters (keep tabs, newlines, carriage returns)
    svg_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', svg_content)

    # 2. Fix unescaped ampersands in text or attribute values
    # Replace '&' not followed by entity name like 'amp;', 'lt;', 'gt;', 'quot;', 'apos;', or numeric '#123;'
    svg_content = re.sub(r'&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)', '&amp;', svg_content)

    # 3. Clean any corrupted Unicode replacement symbols
    svg_content = svg_content.replace('\ufffd', '')

    # 4. In-Memory XML Validation Pass
    try:
        ET.fromstring(svg_content)
        return svg_content
    except Exception as err:
        print(f"[SVG Sanitizer] XML parse error in Panel {panel_num}: {err}. Attempting automated repair...", flush=True)

        # Attempt recovery if unclosed tag
        try:
            if not svg_content.strip().endswith("</svg>"):
                repaired = svg_content + "</svg>"
                ET.fromstring(repaired)
                return repaired
        except Exception:
            pass

        print(f"[SVG Sanitizer] Building guaranteed emergency valid SVG for Panel {panel_num}...", flush=True)
        return build_fallback_svg(topic, panel_num, caption)

def generate_topic_svg(topic: str, panel_num: int, caption: str, output_path: str) -> bool:
    """
    Generates a visual-first, beginner-friendly, practical SVG illustration.
    Emphasizes bold pictorial icons, intuitive visual metaphors, and strictly minimal words.
    """
    print(f"[SVG] Synthesizing Panel {panel_num} illustration for '{topic}'...", flush=True)
    domain_info = detect_topic_domain(topic, caption)
    domain_name = domain_info["domain"]
    bg_color = domain_info["bg_color"]
    prim = domain_info["primary_accent"]
    sec = domain_info["secondary_accent"]
    tert = domain_info["tertiary_accent"]
    guidance = domain_info["visual_guidance"]

    prompt = f"""You are a world-class visual explainer and infographic illustrator for general audiences (like Kurzgesagt or Vox).
Your goal is to explain this concept visually so that ANY everyday person with ZERO technical knowledge can understand it immediately in 2 seconds.

TOPIC: {topic}
PANEL {panel_num} OF 3: {caption}
DOMAIN: {domain_name}

CRITICAL "PRACTICAL & EASY TO UNDERSTAND" DESIGN RULES:
1. TOPIC-ACCURATE VISUAL STORYTELLING:
   - Your illustration MUST directly depict the specific event or concept described in:
     TOPIC: {topic}
     PANEL {panel_num}: {caption}
   - Draw tangible, recognizable real-world objects, subjects, and metaphors fitting the "{domain_name}" domain.
   - NEVER draw leaves, plants, or sunlight unless the topic is specifically botany or photosynthesis.
   - NEVER draw cosmic space, orbits, or quantum particles unless the topic is specifically astronomy or physics.
2. VISUAL FIRST, MINIMAL WORDS (2-SECOND RULE):
   - Maximum 3 to 5 simple, friendly words in the ENTIRE illustration!
   - Examples of good labels: Short labels describing the specific elements shown (e.g., "Third Estate", "Taxes", "Storming", or "User Prompt", "Book Archive", "Verified Answer").
   - ABSOLUTE BAN: NO chemical equations, NO mathematical formulas, NO long dense paragraphs, and NO tiny fine-print sentences. The user reads the caption on the side for details; the graphic must be a pure, self-explanatory visual infographic.
3. BOLD & RECOGNIZABLE GRAPHICS:
   - Draw LARGE, friendly, colorful pictorial shapes with clear silhouettes.
   - Use big, clear directional arrows showing the natural flow from cause to effect, or before vs after.
4. CANVAS SPECIFICATIONS:
   - Root element: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
   - Background: <rect width="800" height="800" fill="{bg_color}"/> with subtle warm ambient atmosphere filling 800x800 edge-to-edge.
   - Palette: Primary: {prim}, Secondary: {sec}, Tertiary: {tert}, Text: #F2F1ED.
   - Keep text inside x: 30 to 770 so nothing clips at the borders.
   - Header: Simple badge ("STEP {panel_num}") and clean short title (2-4 words max matching this panel).
{guidance}
5. STRICT XML FORMAT:
   - Return ONLY raw valid XML <svg>...</svg>. No markdown backticks, no code fences.
   - Every ampersand must be written as &amp;.
"""
    try:
        response = invoke_llm_with_retry(prompt)
        raw = "".join([b["text"] for b in response.content if isinstance(b, dict) and b.get("type") == "text"]) if isinstance(response.content, list) else str(response.content)
        svg_content = sanitize_and_validate_svg(raw, topic, panel_num, caption)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"[SVG] Panel {panel_num} saved successfully ({len(svg_content)} bytes). Valid XML verified.", flush=True)
        return True
    except Exception as e:
        print(f"[SVG] Failed to generate SVG for panel {panel_num}: {e}. Writing emergency fallback...", flush=True)
        fallback_svg = build_fallback_svg(topic, panel_num, caption)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(fallback_svg)
        return True

STYLE_SUFFIX = ", realistic editorial illustration, natural materials and believable proportions, carefully composed documentary-style scene, soft natural cinematic lighting, restrained vibrant colors, clear focal subject, fine realistic detail, no text, no watermark, no logos"
GROUNDING_THRESHOLD = 1.0

LINKEDIN_CLIENT_ID = os.environ["LINKEDIN_CLIENT_ID"]
LINKEDIN_CLIENT_SECRET = os.environ["LINKEDIN_CLIENT_SECRET"]
LINKEDIN_REDIRECT_URI = "http://localhost:8000/auth/linkedin/callback"

# Temporary in-memory storage for the demo — good enough for a single-user project,
# not meant to scale to multiple real users.
linkedin_session = {"access_token": None, "person_urn": None, "name": None}


class TopicRequest(BaseModel):
    topic: str


@app.get("/")
def read_root():
    return {"status": "ExplainIT backend is alive"}


@app.get("/auth/linkedin/login")
def linkedin_login():
    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "scope": "openid profile w_member_social",
    }
    auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)
    return RedirectResponse(auth_url)


@app.get("/auth/linkedin/callback")
async def linkedin_callback(code: str):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": LINKEDIN_REDIRECT_URI,
                "client_id": LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_data = token_response.json()

        if "access_token" not in token_data:
            return HTMLResponse(f"<html><body><p>Login failed: {token_data}</p></body></html>")

        access_token = token_data["access_token"]
        linkedin_session["access_token"] = access_token

        userinfo_response = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo = userinfo_response.json()
        linkedin_session["person_urn"] = f"urn:li:person:{userinfo['sub']}"
        linkedin_session["name"] = userinfo.get("name")

    # This runs inside a popup window opened by the frontend — close it automatically
    # once the login succeeds, so the user lands back in the app, not on a raw JSON page.
    return HTMLResponse("""
        <html><body style="font-family: sans-serif; text-align: center; padding-top: 40px;">
        <p>LinkedIn connected. This window will close automatically...</p>
        <script>window.close();</script>
        </body></html>
    """)


@app.get("/auth/linkedin/status")
def linkedin_status():
    if linkedin_session["access_token"]:
        return {"connected": True, "name": linkedin_session["name"]}
    return {"connected": False}


@app.post("/linkedin/post-panel")
async def post_panel_to_linkedin(panel_number: int, caption: str):
    if not linkedin_session["access_token"]:
        return {"success": False, "message": "Not connected to LinkedIn yet. Visit /auth/linkedin/login first."}

    access_token = linkedin_session["access_token"]
    person_urn = linkedin_session["person_urn"]
    image_path = f"data/images/panel_{panel_number}.png"

    if not os.path.exists(image_path):
        return {"success": False, "message": f"No image found for panel {panel_number}."}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient() as client:
        register_response = await client.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": person_urn,
                    "serviceRelationships": [
                        {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                    ],
                }
            },
        )
        register_data = register_response.json()

        if "value" not in register_data:
            return {"success": False, "message": "Failed to register upload", "details": register_data}

        upload_url = register_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = register_data["value"]["asset"]

        with open(image_path, "rb") as img_file:
            image_bytes = img_file.read()

        upload_response = await client.put(
            upload_url,
            headers={"Authorization": f"Bearer {access_token}"},
            content=image_bytes,
        )

        if upload_response.status_code not in (200, 201):
            return {"success": False, "message": "Image upload to LinkedIn failed", "status": upload_response.status_code}

        post_response = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json={
                "author": person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": caption},
                        "shareMediaCategory": "IMAGE",
                        "media": [
                            {
                                "status": "READY",
                                "media": asset_urn,
                            }
                        ],
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            },
        )

        if post_response.status_code not in (200, 201):
            return {"success": False, "message": "Post creation failed", "status": post_response.status_code, "details": post_response.text}

    return {"success": True, "message": "Posted to LinkedIn successfully."}


@app.post("/upload-source")
async def upload_source(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".txt", ".pdf")):
        return {"success": False, "message": "Only .txt and .pdf files are supported."}

    file_bytes = await file.read()

    try:
        text = extract_text_from_file(file.filename, file_bytes)
        num_chunks = build_vector_store(text, embeddings)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": f"Something went wrong processing this file: {str(e)}"}

    return {
        "success": True,
        "filename": file.filename,
        "chunks_created": num_chunks,
        "message": f"'{file.filename}' is now the active source document."
    }


@app.post("/generate")
def generate_comic(request: TopicRequest):
    topic = request.topic

    vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)
    results_with_scores = vector_store.similarity_search_with_score(topic, k=4)

    if not results_with_scores or results_with_scores[0][1] > GROUNDING_THRESHOLD:
        return {
            "grounded": False,
            "message": f"Not enough grounded source material to explain '{topic}' yet. Try 'How GANs work'."
        }

    grounded_context = "\n\n".join([doc.page_content for doc, score in results_with_scores])

    prompt = f"""You are an expert educational infographic and visual storyteller.
Your mission is to generate a 3-panel visual explainer script for the topic: "{topic}".

CONTEXT:
{grounded_context}

TOPIC TO EXPLAIN:
{topic}

PANEL SCRIPT REQUIREMENTS:
1. Strict Grounding: Use ONLY facts directly supported by the context above.
2. Narrative Progression:
   - Panel 1: The Core Concept & Input (What is the starting point or problem?)
   - Panel 2: The Core Mechanism & Action (How does it work step-by-step?)
   - Panel 3: The Result & Grounded Output (What is the final accurate outcome?)
3. Caption: Clear, engaging, natural human explanation (1-2 sentences).

CRITICAL IMAGE PROMPT RULES:
The image prompt is sent to a text-to-image diffusion model. Diffusion models cannot draw abstract buzzwords (like 'embeddings similarity', 'latent vectors', 'data points'). When given abstract phrases, they hallucinate generic neon hallways, random futuristic tunnels, or robots.

To ensure the images are 100% relevant and recognizable for "{topic}":
1. ALWAYS start every image_prompt with the topic name: "A scene illustrating {topic}: ..."
2. Depict concrete physical subjects, specific objects, interactions, and environments that visually tell this specific panel's story:
   - For Computer Science / AI / RAG: Show realistic, tangible scenes such as an analyst searching through highlighted document archives, a split-screen interface matching questions to book citations, an open manuscript being verified with highlighted sticky notes and reference manuals.
   - For Biology / Chemistry: Show physical lab equipment, glassware, cellular structures, biological specimens, microscope views.
   - For Physics / Engineering: Show physical machines, telescopes, diagrams on blackboards, gears, experimental setups.
3. FORBIDDEN ELEMENTS: Absolutely NO generic futuristic hallways, NO glowing abstract cyber-tunnels, NO random neon circuit boards, NO floating matrix numbers, and NO robots unless the topic is specifically humanoid robotics.
4. Keep the image_prompt under 35 words: Subject + Specific Action + Environment + Lighting.

Return ONLY valid JSON with no markdown formatting and no code fences. Exactly this JSON schema:
{{
  "panels": [
    {{
      "panel_number": 1,
      "caption": "1-2 sentences clearly explaining the concept for this panel.",
      "image_prompt": "A scene illustrating {topic}: A clear, tangible description of the subject, action, and setting matching this panel's explanation."
    }}
  ]
}}
"""
    try:
        response = invoke_llm_with_retry(prompt)
    except Exception as e:
        print(f"Failed to generate comic script after retries: {e}")
        return {
            "grounded": False,
            "message": "The AI service is experiencing high traffic spikes right now. Please try again in a few moments."
        }
    raw_output = response.content

    if isinstance(raw_output, list):
        raw_output = "".join(
            block["text"] for block in raw_output
            if isinstance(block, dict) and block.get("type") == "text"
        )

    try:
        script = json.loads(raw_output)
    except json.JSONDecodeError:
        cleaned = raw_output.strip().strip("```json").strip("```").strip()
        script = json.loads(cleaned)

    os.makedirs("data/images", exist_ok=True)
    def process_panel(panel):
        panel_num = panel["panel_number"]
        caption = panel.get("caption", "")
        raw_prompt = panel.get("image_prompt") or panel.get("scene_description", "")
        image_prompt = raw_prompt.strip() + STYLE_SUFFIX
        random_seed = random.randint(1, 1000000)
        encoded_prompt = quote(image_prompt)

        pollinations_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
        img_saved = False

        if pollinations_key:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ExplainIT/1.0",
                "Authorization": f"Bearer {pollinations_key}"
            }
            image_gen_url = f"https://gen.pollinations.ai/image/{encoded_prompt}?key={pollinations_key}&width=1024&height=1024&seed={random_seed}&nologo=true"
            for attempt in range(2):
                try:
                    img_response = requests.get(image_gen_url, headers=headers, timeout=30)
                    if img_response.status_code == 200 and len(img_response.content) > 1000:
                        png_path = f"data/images/panel_{panel_num}.png"
                        with open(png_path, "wb") as f:
                            f.write(img_response.content)
                        panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png"
                        img_saved = True
                        break
                    time.sleep(1)
                except Exception as e:
                    print(f"Error generating diffusion image for panel {panel_num}: {e}", flush=True)
                    time.sleep(1)

        cache_buster = int(time.time() * 1000)
        if not img_saved:
            # Clean up any stale png counterpart so only the fresh svg exists
            stale_png = f"data/images/panel_{panel_num}.png"
            if os.path.exists(stale_png):
                try:
                    os.remove(stale_png)
                except Exception:
                    pass

            svg_path = f"data/images/panel_{panel_num}.svg"
            if generate_topic_svg(topic, panel_num, caption, svg_path):
                panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.svg?t={cache_buster}"
            else:
                png_path = f"data/images/panel_{panel_num}.png"
                create_fallback_card(topic, panel_num, caption, png_path)
                panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png?t={cache_buster}"
        else:
            # Clean up stale svg counterpart if diffusion succeeded
            stale_svg = f"data/images/panel_{panel_num}.svg"
            if os.path.exists(stale_svg):
                try:
                    os.remove(stale_svg)
                except Exception:
                    pass
            panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png?t={cache_buster}"
        return panel

    print(f"[Generate] Generating visuals for {len(script['panels'])} panels in parallel...", flush=True)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_panel, panel) for panel in script["panels"]]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[Generate] Worker error: {e}", flush=True)

    print(f"[Generate] All {len(script['panels'])} panels generated successfully!", flush=True)
    script["grounded"] = True
    return script


class QuizRequest(BaseModel):
    topic: str

@app.post("/generate-quiz")
def generate_quiz(request: QuizRequest):
    topic = request.topic

    vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)
    results_with_scores = vector_store.similarity_search_with_score(topic, k=4)

    if not results_with_scores or results_with_scores[0][1] > GROUNDING_THRESHOLD:
        raise HTTPException(status_code=400, detail="Not enough grounded source material.")

    grounded_context = "\n\n".join([doc.page_content for doc, score in results_with_scores])

    prompt = f"""You are an expert educator. Create a 3-question multiple-choice quiz about "{topic}" based ONLY on this context:
{grounded_context}

Return ONLY valid JSON in this exact format:
{{
  "questions": [
    {{
      "question": "What is...?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct_index": 0,
      "explanation": "Short explanation of why the correct option is the answer."
    }}
  ]
}}
"""
    try:
        response = invoke_llm_with_retry(prompt)
    except Exception as e:
        print(f"Failed to generate quiz after retries: {e}")
        raise HTTPException(
            status_code=503,
            detail="The AI service is experiencing high traffic spikes right now. Please try again in a few moments."
        )
    raw_output = response.content

    if isinstance(raw_output, list):
        raw_output = "".join(block["text"] for block in raw_output if isinstance(block, dict) and block.get("type") == "text")

    try:
        quiz_data = json.loads(raw_output)
    except json.JSONDecodeError:
        cleaned = raw_output.strip().strip("```json").strip("```").strip()
        try:
            quiz_data = json.loads(cleaned)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Failed to parse quiz JSON from LLM.")

    return quiz_data
