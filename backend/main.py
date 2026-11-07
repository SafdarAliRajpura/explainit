import os
import re
import time
import json
import random
import textwrap
import requests
import httpx
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from fastapi.responses import RedirectResponse, HTMLResponse
from urllib.parse import quote
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from ingest import extract_text_from_file, build_vector_store
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
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


def convert_svg_to_png(svg_path: str, png_path: str):
    """
    Renders SVG to PNG using resvg-py with a solid dark background (#0F1117)
    and RGB color mode for maximum compatibility with image upload APIs.
    """
    try:
        import resvg_py
        import io
        if not os.path.exists(svg_path):
            return False
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        png_bytes = resvg_py.svg_to_bytes(svg_content)
        img = Image.open(io.BytesIO(png_bytes))
        bg = Image.new("RGB", img.size, (15, 17, 23))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        else:
            bg.paste(img)
        bg.save(png_path, "PNG")
        print(f"[SVG->PNG] Rasterized '{svg_path}' to '{png_path}' successfully ({os.path.getsize(png_path)} bytes).", flush=True)
        return True
    except Exception as e:
        print(f"[SVG->PNG] Error rasterizing '{svg_path}': {e}", flush=True)
        return False

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

ACTIVE_MODELS = ["gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
active_models_lock = threading.Lock()

def _call_model_single(model_name: str, prompt: str):
    model = ChatGoogleGenerativeAI(model=model_name, temperature=0.4)
    return model.invoke(prompt)

def invoke_with_hard_timeout(func, args, timeout_sec=25):
    """
    Executes a function in a daemon thread with an absolute, unbreakable timeout.
    Unlike ThreadPoolExecutor, this never blocks on thread termination if a remote socket hangs.
    """
    res = [None]
    err = [None]
    done = threading.Event()

    def worker():
        try:
            res[0] = func(*args)
        except Exception as e:
            err[0] = e
        finally:
            done.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    if not done.wait(timeout=timeout_sec):
        raise TimeoutError(f"Operation timed out after {timeout_sec}s")
    if err[0] is not None:
        raise err[0]
    return res[0]

def invoke_llm_with_retry(prompt: str, max_retries: int = 1, timeout_per_call: int = 25):
    """
    Invokes Google Gemini with guaranteed daemon hard timeout and instant failover across healthy models.
    Prioritizes gemini-3.5-flash for fastest response times.
    """
    global ACTIVE_MODELS
    last_error = None

    with active_models_lock:
        models_to_try = list(ACTIVE_MODELS)

    for model_name in models_to_try:
        for attempt in range(max_retries):
            print(f"[LLM] Requesting model '{model_name}' (timeout: {timeout_per_call}s)...", flush=True)
            try:
                result = invoke_with_hard_timeout(_call_model_single, (model_name, prompt), timeout_sec=timeout_per_call)

                # Prioritize successfully responding model at head of list
                with active_models_lock:
                    if ACTIVE_MODELS and ACTIVE_MODELS[0] != model_name and model_name in ACTIVE_MODELS:
                        ACTIVE_MODELS.remove(model_name)
                        ACTIVE_MODELS.insert(0, model_name)

                print(f"[LLM] Model '{model_name}' responded successfully.", flush=True)
                return result

            except TimeoutError:
                last_error = TimeoutError(f"Call to '{model_name}' timed out after {timeout_per_call}s")
                print(f"[LLM] Hard timeout ({timeout_per_call}s) on '{model_name}'. Immediate failover to next model...", flush=True)
                with active_models_lock:
                    if model_name in ACTIVE_MODELS:
                        ACTIVE_MODELS.remove(model_name)
                        ACTIVE_MODELS.append(model_name)
                break

            except Exception as e:
                last_error = e
                err_msg = str(e)
                print(f"[LLM] Model '{model_name}' error: {err_msg}", flush=True)

                failover_codes = ["503", "504", "DEADLINE_EXCEEDED", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND", "TIMEOUT"]
                if any(code in err_msg for code in failover_codes):
                    print(f"[LLM] '{model_name}' experienced capacity/deadline issue. Immediate failover...", flush=True)
                    with active_models_lock:
                        if model_name in ACTIVE_MODELS:
                            ACTIVE_MODELS.remove(model_name)
                            ACTIVE_MODELS.append(model_name)
                    break
                else:
                    time.sleep(0.5)

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

def detect_layout_archetype(topic: str, caption: str, panel_num: int, prim: str, sec: str, tert: str, card_bg: str = "#161B26", sub_bg: str = "#0F1117", text_col: str = "#F2F1ED") -> dict:
    """
    Selects a distinct, creative, domain-authentic geometric layout archetype for each panel.
    Guarantees that every panel in the 3-panel sequence has a UNIQUE creative visual structure:
    - Panel 1: Input / Setup / Query Interface (The Starting Point)
    - Panel 2: Deep Mechanism / Radar / Transformation Matrix (The Core Engine)
    - Panel 3: Verified Synthesis / Certificate / Payoff (The Grounded Result)
    """
    combined = f"{topic} {caption}".lower()
    domain_info = detect_topic_domain(topic, caption)
    domain_name = domain_info["domain"]

    # 1. SPECIFIC STRUCTURAL OVERRIDES (If explicitly requested in caption)
    tier_pattern = re.compile(
        r'(three estates|3 estates|first estate|second estate|third estate|estates|hierarchy|hierarchical|'
        r'social classes|pyramid|strata|layered|solid.*liquid.*gas|three states|troposphere|stratosphere|3 tiers|three tiers)',
        re.IGNORECASE
    )
    if tier_pattern.search(combined):
        return {
            "archetype_name": "STACKED_3_TIERS",
            "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: STACKED_3_TIERS (3 Distinct Cards Stacked Vertically)
  The concept describes 3 distinct classes, tiers, states, or layers. You MUST draw all 3 distinct cards:
  * Top Card (Tier 1 - 1st Estate / Clergy / Top Layer):
    - Container: <rect x="180" y="150" width="440" height="90" rx="12" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Left Icon: A church/cross/clergy icon centered at (cx: 230, cy: 195)
    - Right Text Block:
      * Card Title: <text x="280" y="185" fill="{text_col}" font-size="18" font-weight="700">1st Estate: Clergy</text>
      * Pill Badge: <rect x="280" y="200" width="180" height="26" rx="6" fill="#10B981" opacity="0.2"/>
                    <text x="370" y="217" fill="#10B981" font-size="12" font-weight="700" text-anchor="middle">0% Taxes • Privileged</text>
  * Middle Card (Tier 2 - 2nd Estate / Nobility / Middle Layer):
    - Container: <rect x="140" y="265" width="520" height="90" rx="12" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Left Icon: A crown/sword/castle icon centered at (cx: 190, cy: 310)
    - Right Text Block:
      * Card Title: <text x="240" y="300" fill="{text_col}" font-size="18" font-weight="700">2nd Estate: Nobility</text>
      * Pill Badge: <rect x="240" y="315" width="180" height="26" rx="6" fill="#10B981" opacity="0.2"/>
                    <text x="330" y="332" fill="#10B981" font-size="12" font-weight="700" text-anchor="middle">0% Taxes • Feudal Rights</text>
  * Crushing Burden Arrow (Middle to Bottom):
    - A bold dashed red downward arrow: <path d="M 400 365 L 400 425" stroke="#EF4444" stroke-width="8" stroke-dasharray="8 6"/> with arrowhead at (400, 435).
    - Centered Arrow Pill: <rect x="325" y="385" width="150" height="28" rx="6" fill="{sub_bg}" stroke="#EF4444" stroke-width="2"/>
      <text x="400" y="404" fill="#EF4444" font-size="12" font-weight="700" text-anchor="middle">100% TAX BURDEN</text>
  * Bottom Card (Tier 3 - 3rd Estate / Commoners - 97% of population bearing the weight):
    - Container: <rect x="80" y="445" width="640" height="150" rx="14" fill="{card_bg}" stroke="{tert}" stroke-width="2.5"/>
    - Left Graphics: 4-5 worker/peasant person silhouettes in a row (cx: 140, 200, 260, 320, cy: 500)
    - Right Text Block:
      * Card Title: <text x="410" y="495" fill="{text_col}" font-size="22" font-weight="800">3rd Estate: Commoners</text>
      * Description Pill: <rect x="410" y="515" width="260" height="32" rx="8" fill="#EF4444" opacity="0.2"/>
        <text x="540" y="536" fill="#EF4444" font-size="13" font-weight="700" text-anchor="middle">97% of People • Pays All Taxes</text>
  * Bottom Summary Pill:
    - <rect x="120" y="650" width="560" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="678" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Deep Inequality: The majority worked to fund the elite</text>
"""
        }

    # 2. COMPUTER SCIENCE, AI & ALGORITHMS (RAG, GANs, LLMs, Neural Nets)
    if domain_name == "COMPUTER SCIENCE & AI":
        if panel_num == 1:
            return {
                "archetype_name": "CS_INPUT_QUERY_INTERFACE",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: CS_INPUT_QUERY_INTERFACE (User Query Interface & Input Flow)
  Focus EXCLUSIVELY on the user's question, prompt, or starting request. DO NOT draw the whole pipeline!
  * Top Card (User Query Dialogue Card):
    - Container: <rect x="90" y="160" width="620" height="180" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Speech Bubble / Search Icon: Centered at (cx: 170, cy: 250) with clean dialogue bubble shape and question mark '?'.
    - Query Label: <text x="240" y="215" fill="{text_col}" font-size="20" font-weight="800">User Prompt / Query</text>
    - Mock Input Field: <rect x="240" y="235" width="430" height="48" rx="10" fill="{sub_bg}" stroke="{sec}" stroke-width="1.5"/>
      <text x="260" y="265" fill="{prim}" font-size="14" font-family="monospace">"What are the verified facts about this topic?"</text>
    - Subtext Badge: <rect x="240" y="295" width="160" height="24" rx="12" fill="{prim}" opacity="0.2"/>
      <text x="320" y="311" fill="{prim}" font-size="11" font-weight="700" text-anchor="middle">Input Intent &amp; Search</text>
  * Central Connecting Pulse:
    - Downward signal arrow from (400, 345) to (400, 420) with dashed stroke="{prim}" stroke-width="4".
    - Pulse indicator: <circle cx="400" cy="382" r="16" fill="{sub_bg}" stroke="{prim}" stroke-width="2"/>
      <text x="400" y="387" fill="{prim}" font-size="14" font-weight="800" text-anchor="middle">↓</text>
  * Bottom Card (Knowledge Pool / Target Corpus):
    - Container: <rect x="90" y="420" width="620" height="210" rx="16" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Left Graphic: Stacked index book / vector database cube grid at (cx: 200, cy: 520).
    - Right Text Block:
      * Section Title: <text x="310" y="480" fill="{text_col}" font-size="20" font-weight="800">Unstructured Knowledge Base</text>
      * Status Pills:
        <rect x="310" y="505" width="220" height="30" rx="8" fill="{sec}" opacity="0.2"/>
        <text x="420" y="525" fill="{sec}" font-size="13" font-weight="700" text-anchor="middle">Indexed Document Library</text>
        <rect x="310" y="545" width="220" height="30" rx="8" fill="#3B82F6" opacity="0.2"/>
        <text x="420" y="565" fill="#3B82F6" font-size="13" font-weight="700" text-anchor="middle">Awaiting Targeted Search</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 1: The user initiates a query that requires accurate retrieval</text>
"""
            }
        elif panel_num == 2:
            return {
                "archetype_name": "CS_VECTOR_RADAR_SCANNER",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: CS_VECTOR_RADAR_SCANNER (Vector Embedding & Search Scanner)
  Focus EXCLUSIVELY on the search, scanning, and chunk comparison mechanism!
  * Left Column (Query Vector Beacon):
    - Container: <rect x="60" y="160" width="200" height="460" rx="16" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Header Badge: <rect x="85" y="185" width="150" height="28" rx="14" fill="{sec}" opacity="0.2"/>
      <text x="160" y="204" fill="{sec}" font-size="12" font-weight="700" text-anchor="middle">QUERY EMBEDDING</text>
    - Icon: Mathematical vector arrow / beacon emitting scanner rays centered at (cx: 160, cy: 330).
    - Status Badge: <rect x="80" y="460" width="160" height="32" rx="8" fill="{sub_bg}" stroke="{sec}" stroke-width="1.5"/>
      <text x="160" y="481" fill="{text_col}" font-size="13" font-weight="700" text-anchor="middle">Semantic Vector [v]</text>
  * Center Column (Vector Radar Space / Scanner Matrix):
    - Container: <rect x="280" y="160" width="240" height="460" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Header Badge: <rect x="310" y="185" width="180" height="28" rx="14" fill="{prim}" opacity="0.2"/>
      <text x="400" y="204" fill="{prim}" font-size="12" font-weight="700" text-anchor="middle">SIMILARITY SCANNER</text>
    - Circular Radar Matrix:
      * Outer circle: <circle cx="400" cy="330" r="85" fill="{sub_bg}" stroke="{prim}" stroke-width="2" stroke-dasharray="6 4"/>
      * Scanner sweep beam: Semi-transparent sector sweep with glowing focal point at (cx: 420, cy: 310).
      * Vector points: Coordinate dots in space with distance connection lines.
    - Status Badge: <rect x="305" y="460" width="190" height="32" rx="8" fill="{sub_bg}" stroke="{prim}" stroke-width="1.5"/>
      <text x="400" y="481" fill="{text_col}" font-size="13" font-weight="700" text-anchor="middle">Cosine Distance Match</text>
  * Right Column (Top Matched Chunks):
    - Container: <rect x="540" y="160" width="200" height="460" rx="16" fill="{card_bg}" stroke="{tert}" stroke-width="2"/>
    - Header Badge: <rect x="565" y="185" width="150" height="28" rx="14" fill="{tert}" opacity="0.2"/>
      <text x="640" y="204" fill="{tert}" font-size="12" font-weight="700" text-anchor="middle">RELEVANT CHUNKS</text>
    - Top Match 1: <rect x="560" y="250" width="160" height="70" rx="10" fill="{sub_bg}" stroke="{tert}" stroke-width="1.5"/>
      <text x="640" y="278" fill="{tert}" font-size="14" font-weight="800" text-anchor="middle">Chunk #1: 98% Match</text>
      <text x="640" y="300" fill="#8B8D93" font-size="11" text-anchor="middle">Exact Source Match</text>
    - Top Match 2: <rect x="560" y="340" width="160" height="70" rx="10" fill="{sub_bg}" stroke="{tert}" stroke-width="1.5"/>
      <text x="640" y="368" fill="{tert}" font-size="14" font-weight="800" text-anchor="middle">Chunk #2: 94% Match</text>
      <text x="640" y="390" fill="#8B8D93" font-size="11" text-anchor="middle">Contextual Match</text>
    - Status Badge: <rect x="560" y="460" width="160" height="32" rx="8" fill="{tert}" opacity="0.2"/>
      <text x="640" y="481" fill="{tert}" font-size="13" font-weight="700" text-anchor="middle">Ranked &amp; Extracted</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 2: Vector search identifies the most accurate chunks from the database</text>
"""
            }
        else: # panel_num == 3
            return {
                "archetype_name": "CS_GROUNDED_VERIFIED_DOCUMENT",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: CS_GROUNDED_VERIFIED_DOCUMENT (Verified Output Certificate with Citations)
  Focus EXCLUSIVELY on the grounded verified output and citation proof!
  * Top Card (Synthesis Engine - Context Injected):
    - Container: <rect x="90" y="160" width="620" height="120" rx="14" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Left Graphic: Retrieved Context Chunks + LLM Reasoning Core (cx: 170, cy: 220) with glowing spark/node icon.
    - Right Text:
      * <text x="250" y="205" fill="{text_col}" font-size="18" font-weight="800">Augmented Prompt Synthesis</text>
      * <rect x="250" y="220" width="240" height="26" rx="6" fill="{sec}" opacity="0.2"/>
        <text x="370" y="238" fill="{sec}" font-size="12" font-weight="700" text-anchor="middle">Context Injected into LLM</text>
  * Connecting Verification Arrow:
    - Downward arrow from (400, 280) to (400, 325) with checkmark circle at (400, 303).
  * Main Hero Certificate (The Grounded Output Document):
    - Container: <rect x="120" y="325" width="560" height="300" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="2.5"/>
    - Document Header:
      * Green Verification Shield: <circle cx="170" cy="370" r="22" fill="#10B981" opacity="0.2"/>
        <path d="M 160 370 L 167 377 L 180 364" fill="none" stroke="#10B981" stroke-width="3" stroke-linecap="round"/>
      * Document Title: <text x="210" y="375" fill="{text_col}" font-size="20" font-weight="800">Grounded Factual Answer</text>
    - Mock Text Lines (Clear Verified Document):
      * Line 1: <rect x="170" y="415" width="460" height="12" rx="6" fill="{sub_bg}"/>
      * Line 2: <rect x="170" y="440" width="420" height="12" rx="6" fill="{sub_bg}"/>
      * Line 3: <rect x="170" y="465" width="340" height="12" rx="6" fill="{sub_bg}"/>
    - Grounding Citation Badges:
      * Badge 1: <rect x="170" y="505" width="160" height="32" rx="8" fill="#10B981" opacity="0.2"/>
        <text x="250" y="526" fill="#10B981" font-size="12" font-weight="700" text-anchor="middle">✓ [1] Verified Citation</text>
      * Badge 2: <rect x="350" y="505" width="160" height="32" rx="8" fill="{tert}" opacity="0.2"/>
        <text x="430" y="526" fill="{tert}" font-size="12" font-weight="700" text-anchor="middle">✓ [2] Primary Source</text>
    - Seal: <rect x="170" y="560" width="460" height="36" rx="8" fill="{sub_bg}" stroke="#10B981" stroke-width="1.5"/>
      <text x="400" y="583" fill="#10B981" font-size="13" font-weight="800" text-anchor="middle">100% FACTUAL • ZERO HALLUCINATIONS</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="#10B981" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 3: The model produces an authentic answer backed by retrieved evidence</text>
"""
            }

    # 3. BIOLOGY & LIFE SCIENCES (Photosynthesis, Cells, Genetics)
    elif domain_name == "BIOLOGY & LIFE SCIENCES":
        if panel_num == 1:
            return {
                "archetype_name": "BIO_INPUT_ABSORPTION",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: BIO_INPUT_ABSORPTION (Natural Energy & Resource Inputs)
  Focus EXCLUSIVELY on the raw inputs being absorbed!
  * Top-Left Radiant Sun: Golden sun at (cx: 200, cy: 230) radiating warm sunlight rays downward toward the leaf.
  * Top-Right Water & Atmosphere: Droplets of water (💧 'Water In') and CO2 molecules drifting into the scene.
  * Center-Bottom Hero Leaf Surface: Large vibrant leaf cutaway (x: 100 to 700, y: 380 to 620) with veins absorbing nutrients.
  * Floating Badges:
    - <rect x="120" y="320" width="160" height="32" rx="16" fill="{prim}" opacity="0.2"/>
      <text x="200" y="341" fill="{prim}" font-size="13" font-weight="700" text-anchor="middle">Sunlight Energy</text>
    - <rect x="520" y="320" width="160" height="32" rx="16" fill="{tert}" opacity="0.2"/>
      <text x="600" y="341" fill="{tert}" font-size="13" font-weight="700" text-anchor="middle">Water &amp; CO2 In</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 1: Leaves absorb sunlight energy, carbon dioxide, and root moisture</text>
"""
            }
        elif panel_num == 2:
            return {
                "archetype_name": "BIO_CHLOROPLAST_ENGINE",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: BIO_CHLOROPLAST_ENGINE (Cellular Factory & Conversion)
  Focus EXCLUSIVELY on the microscopic transformation happening inside the cell!
  * Central Hero Cutaway: Large circular chloroplast membrane cutaway centered at (cx: 400, cy: 380) with r: 180.
  * Inside Chloroplast:
    - Thylakoid coin stacks on left (cx: 320, cy: 380) converting light photons into chemical energy.
    - Calvin cycle circular reaction wheel on right (cx: 470, cy: 380) assembling sugars.
  * Status Pills:
    - <rect x="150" y="180" width="220" height="34" rx="17" fill="{prim}" opacity="0.2"/>
      <text x="260" y="202" fill="{prim}" font-size="13" font-weight="700" text-anchor="middle">Light Reactions (Thylakoids)</text>
    - <rect x="430" y="180" width="220" height="34" rx="17" fill="{sec}" opacity="0.2"/>
      <text x="540" y="202" fill="{sec}" font-size="13" font-weight="700" text-anchor="middle">Calvin Cycle (Sugar Wheel)</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 2: Microscopic cellular machinery transforms light into chemical food</text>
"""
            }
        else: # panel_num == 3
            return {
                "archetype_name": "BIO_THRIVING_PAYOFF",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: BIO_THRIVING_PAYOFF (Oxygen Release & Plant Food)
  Focus EXCLUSIVELY on the final products that sustain life!
  * Left Output Card (Fresh Oxygen Released):
    - Container: <rect x="70" y="180" width="310" height="440" rx="16" fill="{card_bg}" stroke="{tert}" stroke-width="2"/>
    - Floating oxygen bubbles drifting upward into clean blue sky.
    - Badge: <rect x="105" y="470" width="240" height="36" rx="8" fill="{tert}" opacity="0.2"/>
      <text x="225" y="493" fill="{tert}" font-size="14" font-weight="700" text-anchor="middle">Fresh Oxygen Released (O2)</text>
  * Right Output Card (Glucose / Plant Sugar Fuel):
    - Container: <rect x="420" y="180" width="310" height="440" rx="16" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Radiant golden energy crystal / plant sugar star.
    - Badge: <rect x="455" y="470" width="240" height="36" rx="8" fill="{sec}" opacity="0.2"/>
      <text x="575" y="493" fill="{sec}" font-size="14" font-weight="700" text-anchor="middle">Plant Food &amp; Energy (Sugar)</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 3: Plants release clean oxygen into the atmosphere and nourish growth</text>
"""
            }

    # 4. HISTORY, POLITICS & SOCIETY
    elif domain_name == "HISTORY, POLITICS & SOCIETY":
        if panel_num == 1:
            return {
                "archetype_name": "2_COLUMN_SPLIT",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: 2_COLUMN_SPLIT (Balanced Side-by-Side Symmetrical Columns)
  Compare cause and effect side-by-side with equal balance:
  * Left Card (Cause / Debt / Input):
    - Container: <rect x="70" y="160" width="310" height="460" rx="16" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Card Header Badge: <rect x="100" y="185" width="150" height="30" rx="15" fill="{sec}" opacity="0.2"/>
      <text x="175" y="205" fill="{sec}" font-size="12" font-weight="700" text-anchor="middle">WAR COSTS</text>
    - Central Icon: Centered inside Left Card at (cx: 225, cy: 330) with r: 70 (e.g. Empty Royal Treasury Vault with low fallen coins).
    - Status Badge: <rect x="110" y="450" width="230" height="36" rx="8" fill="{sub_bg}" stroke="{sec}" stroke-width="1.5"/>
      <text x="225" y="473" fill="{text_col}" font-size="14" font-weight="700" text-anchor="middle">Empty State Treasury</text>
    - Metric Pill: <text x="225" y="525" fill="#EF4444" font-size="13" font-weight="600" text-anchor="middle">Bankruptcy Imminent</text>
  * Center Transition / Impact:
    - Flow Arrow: <path d="M 390 390 L 410 390 M 403 383 L 410 390 L 403 397" stroke="#F2F1ED" stroke-width="4" stroke-linecap="round"/>
    - Impact Badge: <circle cx="400" cy="340" r="18" fill="{sub_bg}" stroke="{tert}"/>
      <text x="400" y="345" fill="{tert}" font-size="14" font-weight="800" text-anchor="middle">→</text>
  * Right Card (Burden / Unfair Taxes / Output):
    - Container: <rect x="420" y="160" width="310" height="460" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Card Header Badge: <rect x="450" y="185" width="150" height="30" rx="15" fill="{prim}" opacity="0.2"/>
      <text x="525" y="205" fill="{prim}" font-size="12" font-weight="700" text-anchor="middle">UNFAIR TAXES</text>
    - Central Icon: Centered inside Right Card at (cx: 575, cy: 330) with r: 70 (e.g. Tilted Scale of Injustice).
    - Status Badge: <rect x="460" y="450" width="230" height="36" rx="8" fill="{sub_bg}" stroke="{prim}" stroke-width="1.5"/>
      <text x="575" y="473" fill="{text_col}" font-size="14" font-weight="700" text-anchor="middle">Crushing Tax System</text>
    - Metric Pill: <text x="575" y="525" fill="{tert}" font-size="13" font-weight="600" text-anchor="middle">Commoners Carry 100%</text>
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Heavy war expenses triggered extreme, unequal taxation</text>
"""
            }
        elif panel_num == 2:
            return {
                "archetype_name": "STACKED_3_TIERS",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: STACKED_3_TIERS (3 Distinct Cards Stacked Vertically)
  The concept describes 3 distinct classes, tiers, states, or layers. You MUST draw all 3 distinct cards:
  * Top Card (Tier 1 - 1st Estate / Clergy / Top Layer):
    - Container: <rect x="180" y="150" width="440" height="90" rx="12" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Left Icon: A church/cross/clergy icon centered at (cx: 230, cy: 195)
    - Right Text Block:
      * Card Title: <text x="280" y="185" fill="{text_col}" font-size="18" font-weight="700">1st Estate: Clergy</text>
      * Pill Badge: <rect x="280" y="200" width="180" height="26" rx="6" fill="#10B981" opacity="0.2"/>
                    <text x="370" y="217" fill="#10B981" font-size="12" font-weight="700" text-anchor="middle">0% Taxes • Privileged</text>
  * Middle Card (Tier 2 - 2nd Estate / Nobility / Middle Layer):
    - Container: <rect x="140" y="265" width="520" height="90" rx="12" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Left Icon: A crown/sword/castle icon centered at (cx: 190, cy: 310)
    - Right Text Block:
      * Card Title: <text x="240" y="300" fill="{text_col}" font-size="18" font-weight="700">2nd Estate: Nobility</text>
      * Pill Badge: <rect x="240" y="315" width="180" height="26" rx="6" fill="#10B981" opacity="0.2"/>
                    <text x="330" y="332" fill="#10B981" font-size="12" font-weight="700" text-anchor="middle">0% Taxes • Feudal Rights</text>
  * Crushing Burden Arrow (Middle to Bottom):
    - A bold dashed red downward arrow: <path d="M 400 365 L 400 425" stroke="#EF4444" stroke-width="8" stroke-dasharray="8 6"/> with arrowhead at (400, 435).
    - Centered Arrow Pill: <rect x="325" y="385" width="150" height="28" rx="6" fill="{sub_bg}" stroke="#EF4444" stroke-width="2"/>
      <text x="400" y="404" fill="#EF4444" font-size="12" font-weight="700" text-anchor="middle">100% TAX BURDEN</text>
  * Bottom Card (Tier 3 - 3rd Estate / Commoners - 97% of population bearing the weight):
    - Container: <rect x="80" y="445" width="640" height="150" rx="14" fill="{card_bg}" stroke="{tert}" stroke-width="2.5"/>
    - Left Graphics: 4-5 worker/peasant person silhouettes in a row (cx: 140, 200, 260, 320, cy: 500)
    - Right Text Block:
      * Card Title: <text x="410" y="495" fill="{text_col}" font-size="22" font-weight="800">3rd Estate: Commoners</text>
      * Description Pill: <rect x="410" y="515" width="260" height="32" rx="8" fill="#EF4444" opacity="0.2"/>
        <text x="540" y="536" fill="#EF4444" font-size="13" font-weight="700" text-anchor="middle">97% of People • Pays All Taxes</text>
  * Bottom Summary Pill:
    - <rect x="120" y="650" width="560" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="678" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Deep Inequality: The majority worked to fund the elite</text>
"""
            }
        else: # panel_num == 3
            return {
                "archetype_name": "HERO_FOCUS_CALLOUTS",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: HERO_FOCUS_CALLOUTS (Centered Dramatic Scene with Anchored Callouts)
  Center the dramatic action along the central axis (x: 400) without disconnected floating stickers:
  * Top Focal Subject (Monarchy / Collapsing Old Order):
    - Centered at x: 400, y: 170 to 250.
    - Large golden royal crown tilted/falling (x: 400, y: 200) with glowing highlights.
    - Anchored status pill directly under crown: <rect x="310" y="235" width="180" height="28" rx="14" fill="{card_bg}" stroke="#EF4444" stroke-width="1.5"/>
      <text x="400" y="253" fill="#EF4444" font-size="12" font-weight="700" text-anchor="middle">Monarchy Overthrown</text>
  * Middle Dramatic Clash / Gate:
    - Fortress stone battlements and archway centered at x: 400, y: 300 to 420.
    - Energy spark / shattered chains / open iron gates centered at (cx: 400, cy: 380).
  * Bottom Dynamic Advancing Crowd:
    - Advancing crowd silhouettes centered at x: 400, y: 460 to 600.
    - Dynamic crowd figures: Center leader holding flag high (x: 400, y: 490), flanked by supporters on left and right.
    - Anchored crowd pill: <rect x="310" y="590" width="180" height="30" rx="15" fill="#3B82F6" opacity="0.2"/>
      <text x="400" y="610" fill="#3B82F6" font-size="13" font-weight="800" text-anchor="middle">Third Estate United</text>
  * ABSOLUTELY NO UNATTACHED FLOATING CORNER BADGES!
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="#EF4444" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">July 1789: The People Rise to Claim Liberty and Equality</text>
"""
            }

    # 5. GENERAL PROCESS & MECHANISM (Every panel has a unique role)
    else:
        if panel_num == 1:
            return {
                "archetype_name": "GENERAL_INPUT_SETUP",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: GENERAL_INPUT_SETUP (The Problem & Starting State)
  Focus strictly on the starting state or input! Do NOT draw future stages!
  * Top Card (Starting Condition / User Need):
    - Container: <rect x="90" y="160" width="620" height="200" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
    - Icon at left (cx: 170, cy: 260) representing the starting condition or input.
    - Title at (x: 250, y: 230), status pill at (x: 250, y: 270).
  * Downward Connection Flow:
    - Direct signal arrow pointing from top card to the bottom environment.
  * Bottom Card (Initial Context / Resource Pool):
    - Container: <rect x="90" y="420" width="620" height="210" rx="16" fill="{card_bg}" stroke="{sec}" stroke-width="2"/>
    - Graphic of initial materials / environment awaiting processing.
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 1: Establishing the baseline condition and input</text>
"""
            }
        elif panel_num == 2:
            return {
                "archetype_name": "GENERAL_TRANSFORMATION_ENGINE",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: GENERAL_TRANSFORMATION_ENGINE (The Transformation Core)
  Focus strictly on the internal mechanism, reaction chamber, or processing engine!
  * Central Transformation Core:
    - Large circular or octagonal processing matrix centered at (cx: 400, cy: 380) with r: 170.
    - Input feed arriving from left, active transformation gears/matrix in center, converted output emerging on right.
  * Clear status badges indicating the active conversion taking place.
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{sec}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 2: Core mechanism actively processes and transforms the input</text>
"""
            }
        else: # panel_num == 3
            return {
                "archetype_name": "GENERAL_VERIFIED_OUTCOME",
                "layout_instructions": f"""
- MANDATORY GEOMETRIC LAYOUT: GENERAL_VERIFIED_OUTCOME (The Final Payoff & Verified Result)
  Focus strictly on the final result, comparison, or verified achievement!
  * Symmetrical Split (Before vs After, or Raw Input vs Final Achievement) or Hero Certificate showcase.
  * Clean verification badges and achievement metrics.
  * Bottom Summary Pill:
    - <rect x="100" y="660" width="600" height="46" rx="23" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
    - <text x="400" y="688" fill="{text_col}" font-size="14" font-weight="600" text-anchor="middle">Step 3: Successful, verified outcome achieved</text>
"""
            }

STYLE_CONFIGS = {
    "comic": {
        "name": "Classic Comic",
        "diffusion_suffix": ", classic comic book art, bold dynamic ink lineart, vibrant flat halftone colors, retro graphic novel aesthetic, pop-art crosshatching, dramatic panel lighting, no text, no watermark, no logos",
        "svg_bg": "#181412",
        "card_bg": "#251D19",
        "sub_bg": "#14100E",
        "primary": "#FFB800",
        "secondary": "#EF4444",
        "tertiary": "#10B981",
        "accent": "#F59E0B",
        "text": "#FFF8E7",
        "visual_guidance": "Vibrant comic-book graphic novel aesthetic with punchy dynamic badge borders, clean flat fills, and expressive iconic outlines.",
        "svg_embellishments": """- BOLD COMIC INK: Give main cards a thick, punchy border (stroke="{prim}" stroke-width="3") with a solid offset ink shadow (<rect fill="#000000" opacity="0.6"/> offset +4px, +4px).
- COMIC BURST BADGES: Use jagged comic explosion badges or retro comic caption boxes (<rect rx="6" .../>) for titles and step markers.
- DYNAMIC ACTION: Use bold arrows with triangular arrowhead polygons, comic action lines, and high-energy focal points.
- TYPOGRAPHY: Clean, modern, highly legible sans-serif lettering (font-family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"). Use font-weight="600" for titles and badges, and font-weight="500" or "400" for descriptions. NEVER use heavy or compressed fonts like Impact or Arial Black, and NEVER use font-weight="900" or "800"."""
    },
    "blueprint": {
        "name": "Technical Blueprint",
        "diffusion_suffix": ", technical engineering blueprint style, deep cyan and navy monochrome schematic, clean grid lines, isometric architectural draft aesthetic, subtle chalkboard texture, precision instrumentation, no text, no watermark, no logos",
        "svg_bg": "#0B192C",
        "card_bg": "#0F2644",
        "sub_bg": "#071424",
        "primary": "#00D2DF",
        "secondary": "#5483B3",
        "tertiary": "#93C5FD",
        "accent": "#00F0FF",
        "text": "#E0F2FE",
        "visual_guidance": "Technical schematic blueprint aesthetic with crisp coordinate grids, isometric block diagrams, cyan vector lines, and precision engineering annotations.",
        "svg_embellishments": """- TECHNICAL BLUEPRINT GRID: Add an authentic drafting grid in <defs>:
  <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
    <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#163252" stroke-width="0.75"/>
    <path d="M 160 0 L 0 0 0 160" fill="none" stroke="#224C7A" stroke-width="1.25"/>
  </pattern>
  And put <rect width="800" height="800" fill="url(#grid)"/> directly over the background!
- DRAFTING SCHEMATICS: Draw precision engineering vector lines (stroke="{prim}" stroke-width="1.5" stroke-dasharray="6 3"), measurement dimension lines with technical arrows (<--->), and crosshairs (+) at key coordinate points.
- ENGINEERING ANNOTATIONS: Technical labels formatted as coordinates, e.g. "[ SEC-01 // FIG. 1.0 ]" in crisp technical monospace (font-family="'SF Mono', 'Courier New', monospace")."""
    },
    "watercolor": {
        "name": "Editorial Watercolor",
        "diffusion_suffix": ", modern editorial watercolor illustration, soft pigment washes, delicate textured cotton paper, elegant organic brush strokes, muted contemporary palette, high-end science journal cover art, soft natural daylight, no text, no watermark, no logos",
        "svg_bg": "#1C1917",
        "card_bg": "#2A221E",
        "sub_bg": "#171412",
        "primary": "#F4A261",
        "secondary": "#E76F51",
        "tertiary": "#2A9D8F",
        "accent": "#E9C46A",
        "text": "#FAF7F2",
        "visual_guidance": "Artistic modern editorial watercolor aesthetic with soft warm gradients, organic rounded badge frames, and elegant minimalist diagrams.",
        "svg_embellishments": """- WATERCOLOR PIGMENT WASHES: Add soft radial gradients in <defs> to simulate artistic watercolor pigment bleeds:
  <radialGradient id="washGrad" cx="50%" cy="45%" r="60%">
    <stop offset="0%" stop-color="{prim}" stop-opacity="0.35"/>
    <stop offset="50%" stop-color="{sec}" stop-opacity="0.12"/>
    <stop offset="100%" stop-color="{bg_color}" stop-opacity="0"/>
  </radialGradient>
  Use smooth circular washes under key elements.
- ORGANIC MINIMALISM: Use generous rounded capsules (rx="28"), delicate thin strokes (stroke-width="1.2"), and hand-drawn organic curve paths (d="M ... C ...").
- EDITORIAL PALETTE: Earthy warm terracotta, muted sage teal, and warm ochre tones. Clean elegant typography (font-family="Georgia, 'Times New Roman', serif")."""
    },
    "cyberpunk": {
        "name": "Retro Cyberpunk",
        "diffusion_suffix": ", retro cyberpunk style, dark synthwave noir, glowing neon cyan and hot magenta rim lighting, dark reflective rainy textures, 80s futuristic HUD terminal aesthetic, high contrast, cinematic atmosphere, no text, no watermark, no logos",
        "svg_bg": "#0A0A10",
        "card_bg": "#141322",
        "sub_bg": "#08080E",
        "primary": "#00F0FF",
        "secondary": "#FF007F",
        "tertiary": "#FFE600",
        "accent": "#BD00FF",
        "text": "#00FFCC",
        "visual_guidance": "Cyberpunk terminal HUD aesthetic with dark space background, vivid neon wireframe boxes, glowing status pills, and high-tech circuitry cues.",
        "svg_embellishments": """- NEON GLOW FILTER: Add an authentic SVG glow filter in <defs>:
  <filter id="neonGlow" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="3.5" result="coloredBlur"/>
    <feMerge>
      <feMergeNode in="coloredBlur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  Apply filter="url(#neonGlow)" to prominent glowing cyan ({prim}) and hot magenta ({sec}) stroke paths!
- HUD SCANLINES & BRACKETS: Draw futuristic HUD corner brackets [ ┌ ┐ └ ┘ ] around primary containers.
- HIGH-TECH TELEMETRY: Glowing status pills with blinking indicators, sci-fi telemetry badges "[ SYS_DIAG // v2.4 ]", and luminous circuit traces in monospace."""
    }
}

AUDIENCE_CONFIGS = {
    "eli5": {
        "name": "ELI5 (Beginner)",
        "tone_prompt": """AUDIENCE LEVEL: ELI5 (Explain Like I'm 5 / Complete Beginner).
- Tone: Playful, warm, clear, vivid, and memorable.
- Analogy Requirement: Use a strong everyday metaphor or analogy (e.g. kitchen recipes, detective & art forger, playgrounds, puzzle pieces, sports).
- Vocabulary: Zero intimidating academic jargon. If you must use a technical term, define it instantly with a simple metaphor.
- Captions must feel exciting, accessible, and delightful to a beginner or child.""",
        "quiz_prompt": "Craft fun, friendly, and intuitive multiple-choice questions focusing on the central metaphors and concepts. Keep phrasing upbeat and easy to understand.",
        "linkedin_prompt": "Write with a friendly, highly accessible 'ELI5 / simplified breakdown' voice that anyone from beginners to curious learners can instantly grasp and enjoy."
    },
    "college": {
        "name": "College (Standard)",
        "tone_prompt": """AUDIENCE LEVEL: College / General Tech Audience (Standard).
- Tone: Engaging, structured, and informative.
- Narrative: Clear step-by-step mechanism breakdown: starting input/problem -> core transformation/action -> validated final outcome.
- Vocabulary: Standard foundational concepts, clear terminology, and practical real-world context.""",
        "quiz_prompt": "Craft balanced questions testing conceptual comprehension and core mechanics.",
        "linkedin_prompt": "Write with a sharp, professional educational voice tailored for curious professionals and students."
    },
    "pro": {
        "name": "Senior Engineer (Pro)",
        "tone_prompt": """AUDIENCE LEVEL: Senior Engineer / Technical Expert (Deep Dive).
- Tone: Rigorous, analytical, direct, and architecture-focused.
- Technical Rigor: Highlight specific algorithmic mechanisms, objective functions/mathematical formulations, system bottlenecks, latency vs. throughput tradeoffs, and edge case handling.
- Vocabulary: Industry-grade terminology (e.g., loss divergence, backprop gradients, state space, memory complexity).""",
        "quiz_prompt": "Craft advanced technical scenario questions testing architectural understanding, tradeoffs, and system constraints.",
        "linkedin_prompt": "Write with an authoritative, engineering-grade perspective focusing on system architecture, operational tradeoffs, and deep technical insights."
    }
}

def build_fallback_svg(topic: str, panel_num: int, caption: str, style: str = "comic") -> str:
    """
    Constructs an editorial, guaranteed-valid SVG graphic directly in Python.
    Guarantees 0% broken images with a stunning, style-authentic visual presentation.
    """
    style_cfg = STYLE_CONFIGS.get(style, STYLE_CONFIGS["comic"])
    bg_color = style_cfg["svg_bg"]
    card_bg = style_cfg.get("card_bg", "#161B26")
    sub_bg = style_cfg.get("sub_bg", "#0F1117")
    prim = style_cfg["primary"]
    sec = style_cfg["secondary"]
    tert = style_cfg["tertiary"]
    accent = style_cfg["accent"]
    text_col = style_cfg["text"]

    clean_topic = topic.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    clean_caption = caption.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    wrapped_lines = textwrap.wrap(clean_caption, width=46)[:4]
    caption_tspan = "".join(f'<tspan x="80" dy="24">{line}</tspan>' for line in wrapped_lines)

    if style == "blueprint":
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <pattern id="bpGrid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#163252" stroke-width="0.75"/>
      <path d="M 160 0 L 0 0 0 160" fill="none" stroke="#224C7A" stroke-width="1.25"/>
    </pattern>
  </defs>
  <rect width="800" height="800" fill="{bg_color}"/>
  <rect width="800" height="800" fill="url(#bpGrid)"/>
  <rect x="24" y="24" width="752" height="752" rx="4" fill="none" stroke="{prim}" stroke-width="1.5" stroke-dasharray="16 8"/>

  <rect x="50" y="50" width="260" height="32" rx="4" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
  <text x="180" y="71" fill="{prim}" font-family="'SF Mono', 'Courier New', monospace" font-size="12" font-weight="700" text-anchor="middle" letter-spacing="1.5">[ SCHEMATIC: STEP {panel_num} // ISO-26 ]</text>
  <text x="50" y="125" fill="{text_col}" font-family="'SF Mono', 'Courier New', monospace" font-size="24" font-weight="700">{clean_topic}</text>

  <rect x="120" y="180" width="560" height="400" rx="8" fill="{card_bg}" stroke="{prim}" stroke-width="2"/>
  <path d="M 120 180 L 160 140 L 720 140 L 680 180" fill="#0C1F38" stroke="{sec}" stroke-width="1.5"/>
  <path d="M 720 140 L 720 540 L 680 580" fill="#08182D" stroke="{sec}" stroke-width="1.5"/>

  <circle cx="400" cy="380" r="140" fill="none" stroke="{sec}" stroke-width="1.5" stroke-dasharray="6 4"/>
  <circle cx="400" cy="380" r="90" fill="none" stroke="{prim}" stroke-width="2"/>
  <circle cx="400" cy="380" r="40" fill="{sub_bg}" stroke="{prim}" stroke-width="1.5"/>
  <circle cx="400" cy="380" r="8" fill="{prim}"/>

  <path d="M 370 380 L 430 380 M 400 350 L 400 410" stroke="{prim}" stroke-width="2"/>
  <path d="M 230 380 L 250 380 M 550 380 L 570 380 M 400 210 L 400 230 M 400 530 L 400 550" stroke="{sec}" stroke-width="1.5"/>
  <text x="400" y="325" fill="{prim}" font-family="'SF Mono', monospace" font-size="12" font-weight="700" text-anchor="middle">COORD: 400x380 // DATA BUS</text>

  <rect x="50" y="620" width="700" height="120" rx="6" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
  <rect x="70" y="635" width="160" height="22" rx="4" fill="{sub_bg}" stroke="{sec}" stroke-width="1"/>
  <text x="150" y="650" fill="{sec}" font-family="'SF Mono', monospace" font-size="10" font-weight="700" text-anchor="middle">&gt; TECHNICAL SPECIFICATION</text>
  <text x="80" y="685" fill="{text_col}" font-family="'SF Mono', 'Courier New', monospace" font-size="14">
    {caption_tspan}
  </text>
</svg>"""

    elif style == "cyberpunk":
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <filter id="cyberGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="800" height="800" fill="{bg_color}"/>
  <rect x="24" y="24" width="752" height="752" rx="10" fill="none" stroke="{prim}" stroke-width="1.5" opacity="0.6"/>

  <path d="M 40 70 L 40 40 L 70 40 M 760 70 L 760 40 L 730 40 M 40 730 L 40 760 L 70 760 M 760 730 L 760 760 L 730 760" fill="none" stroke="{sec}" stroke-width="3" filter="url(#cyberGlow)"/>

  <rect x="50" y="50" width="240" height="30" rx="4" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
  <circle cx="68" cy="65" r="5" fill="{sec}" filter="url(#cyberGlow)"/>
  <text x="165" y="70" fill="{prim}" font-family="'Courier New', monospace" font-size="12" font-weight="600" text-anchor="middle" letter-spacing="2">SYS_TELEMETRY // P-0{panel_num}</text>
  <text x="50" y="125" fill="{text_col}" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="600" letter-spacing="0.5">{clean_topic}</text>

  <rect x="100" y="180" width="600" height="410" rx="14" fill="{card_bg}" stroke="{sec}" stroke-width="2" filter="url(#cyberGlow)"/>
  <circle cx="400" cy="385" r="130" fill="none" stroke="{prim}" stroke-width="2" stroke-dasharray="12 6" filter="url(#cyberGlow)"/>
  <circle cx="400" cy="385" r="80" fill="{sub_bg}" stroke="{tert}" stroke-width="2"/>
  <polygon points="400,320 455,385 400,450 345,385" fill="{sec}" opacity="0.3" stroke="{sec}" stroke-width="2"/>
  <circle cx="400" cy="385" r="14" fill="{prim}" filter="url(#cyberGlow)"/>

  <path d="M 140 385 L 240 385 M 560 385 L 660 385" stroke="{prim}" stroke-width="3" stroke-linecap="round"/>
  <rect x="300" y="210" width="200" height="26" rx="13" fill="{sub_bg}" stroke="{tert}" stroke-width="1.5"/>
  <text x="400" y="227" fill="{tert}" font-family="'Courier New', monospace" font-size="11" font-weight="600" text-anchor="middle">ACTIVE_NEURAL_LINK</text>

  <rect x="50" y="620" width="700" height="120" rx="8" fill="{card_bg}" stroke="{prim}" stroke-width="1.5"/>
  <rect x="70" y="635" width="170" height="22" rx="4" fill="{sub_bg}" stroke="{sec}" stroke-width="1"/>
  <text x="155" y="650" fill="{sec}" font-family="'Courier New', monospace" font-size="10" font-weight="600" text-anchor="middle">// DECRYPTED STREAM</text>
  <text x="80" y="685" fill="{text_col}" font-family="'Courier New', monospace" font-size="14" font-weight="700">
    {caption_tspan}
  </text>
</svg>"""

    elif style == "watercolor":
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <defs>
    <radialGradient id="waterWash" cx="50%" cy="45%" r="60%">
      <stop offset="0%" stop-color="{prim}" stop-opacity="0.35"/>
      <stop offset="50%" stop-color="{sec}" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="{bg_color}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="800" height="800" fill="{bg_color}"/>
  <circle cx="400" cy="380" r="300" fill="url(#waterWash)"/>
  <rect x="24" y="24" width="752" height="752" rx="24" fill="none" stroke="{prim}" stroke-width="1.5" opacity="0.4"/>

  <rect x="50" y="50" width="180" height="34" rx="17" fill="{card_bg}" stroke="{prim}" stroke-width="1.2"/>
  <text x="140" y="72" fill="{prim}" font-family="Georgia, serif" font-size="13" font-style="italic" font-weight="700" text-anchor="middle">Panel {panel_num} • Editorial</text>
  <text x="50" y="125" fill="{text_col}" font-family="Georgia, serif" font-size="26" font-weight="700">{clean_topic}</text>

  <rect x="110" y="170" width="580" height="420" rx="32" fill="{card_bg}" stroke="{sec}" stroke-width="1.5" opacity="0.95"/>
  <circle cx="400" cy="380" r="140" fill="none" stroke="{prim}" stroke-width="2.5" opacity="0.7"/>
  <circle cx="400" cy="380" r="95" fill="none" stroke="{tert}" stroke-width="1.5" stroke-dasharray="8 6"/>
  <circle cx="400" cy="380" r="50" fill="{sub_bg}" stroke="{accent}" stroke-width="2"/>
  <circle cx="400" cy="380" r="16" fill="{prim}"/>

  <circle cx="280" cy="300" r="24" fill="{sub_bg}" stroke="{tert}" stroke-width="1.5"/>
  <circle cx="520" cy="460" r="24" fill="{sub_bg}" stroke="{sec}" stroke-width="1.5"/>
  <path d="M 298 315 C 340 350, 360 360, 385 375" fill="none" stroke="{prim}" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M 415 385 C 440 400, 470 420, 502 448" fill="none" stroke="{sec}" stroke-width="1.5" stroke-linecap="round"/>

  <rect x="50" y="620" width="700" height="120" rx="24" fill="{card_bg}" stroke="{sec}" stroke-width="1.2"/>
  <rect x="80" y="635" width="130" height="24" rx="12" fill="{sub_bg}" stroke="{prim}" stroke-width="1"/>
  <text x="145" y="651" fill="{prim}" font-family="Georgia, serif" font-size="11" font-weight="700" text-anchor="middle">EXPLANATION</text>
  <text x="80" y="688" fill="{text_col}" font-family="Georgia, serif" font-size="15" font-style="italic">
    {caption_tspan}
  </text>
</svg>"""

    else:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
  <rect width="800" height="800" fill="{bg_color}"/>
  
  <rect x="32" y="32" width="744" height="744" rx="16" fill="#000000" opacity="0.6"/>
  <rect x="24" y="24" width="744" height="744" rx="16" fill="{card_bg}" stroke="{prim}" stroke-width="3"/>

  <rect x="50" y="48" width="170" height="36" rx="6" fill="{prim}" stroke="#000000" stroke-width="2"/>
  <text x="135" y="72" fill="#000000" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="600" text-anchor="middle" letter-spacing="1">STEP {panel_num}</text>
  <text x="50" y="125" fill="{text_col}" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="600">{clean_topic}</text>

  <rect x="106" y="176" width="596" height="426" rx="12" fill="#000000" opacity="0.6"/>
  <rect x="100" y="170" width="596" height="426" rx="12" fill="{sub_bg}" stroke="{sec}" stroke-width="3"/>

  <circle cx="400" cy="380" r="140" fill="none" stroke="{prim}" stroke-width="4"/>
  <circle cx="400" cy="380" r="100" fill="none" stroke="{sec}" stroke-width="3" stroke-dasharray="10 8"/>
  <polygon points="400,280 425,350 500,350 440,395 465,470 400,425 335,470 360,395 300,350 375,350" fill="{prim}" stroke="#000000" stroke-width="2"/>
  <circle cx="400" cy="380" r="22" fill="{sec}" stroke="#FFFFFF" stroke-width="2"/>

  <rect x="56" y="626" width="696" height="116" rx="8" fill="#000000" opacity="0.6"/>
  <rect x="50" y="620" width="696" height="116" rx="8" fill="{card_bg}" stroke="{prim}" stroke-width="2.5"/>
  <rect x="70" y="632" width="120" height="24" rx="4" fill="{sec}"/>
  <text x="130" y="648" fill="#FFFFFF" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="600" text-anchor="middle">PANEL {panel_num}</text>
  <text x="80" y="682" fill="{text_col}" font-family="system-ui, -apple-system, sans-serif" font-size="15" font-weight="700">
    {caption_tspan}
  </text>
</svg>"""

def sanitize_and_validate_svg(raw: str, topic: str, panel_num: int, caption: str, style: str = "comic") -> str:
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



    # 4. Remove ghost shadow text with low opacity
    svg_content = re.sub(r"""<text\b[^>]*\bopacity=['"](?:0\.[0-3]\d*|\.[0-3]\d*)['"][^>]*>[\s\S]*?<\/text>""", "", svg_content)

    # 5. Normalize SVG Typography: Replace heavy/compressed display fonts (Impact, Arial Black) with clean modern sans-serif
    svg_content = re.sub(
        r"""font-family\s*=\s*['"][^'"]*?(?:Impact|Arial\s+Black)[^'"]*?['"]""",
        'font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, sans-serif"',
        svg_content,
        flags=re.IGNORECASE
    )

    # 6. Clamp heavy font weights (900, 800, bold, bolder, black, heavy) to balanced 600
    svg_content = re.sub(
        r"""font-weight\s*=\s*['"](?:900|800|bold|bolder|black|heavy)['"]""",
        'font-weight="600"',
        svg_content,
        flags=re.IGNORECASE
    )

    # 7. Clamp inline styles if any
    svg_content = re.sub(
        r"""font-weight\s*:\s*(?:900|800|bold|bolder|black|heavy)""",
        'font-weight: 600',
        svg_content,
        flags=re.IGNORECASE
    )
    svg_content = re.sub(
        r"""font-family\s*:\s*[^;"]*?(?:Impact|Arial\s+Black)[^;"]*?""",
        'font-family: system-ui, -apple-system, sans-serif;',
        svg_content,
        flags=re.IGNORECASE
    )

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
        return build_fallback_svg(topic, panel_num, caption, style=style)

def generate_topic_svg(topic: str, panel_num: int, caption: str, output_path: str, style: str = "comic") -> bool:
    """
    Generates a visual-first, beginner-friendly, practical SVG illustration with
    strict geometric layout archetypes to guarantee zero text overlap and perfect alignment.
    """
    try:
        print(f"[SVG] Synthesizing Panel {panel_num} illustration for '{topic}' in style '{style}'...", flush=True)
        domain_info = detect_topic_domain(topic, caption)
        domain_name = domain_info["domain"]
        guidance = domain_info.get("visual_guidance", "")

        style_cfg = STYLE_CONFIGS.get(style, STYLE_CONFIGS["comic"])
        bg_color = style_cfg["svg_bg"]
        card_bg = style_cfg.get("card_bg", "#161B26")
        sub_bg = style_cfg.get("sub_bg", "#0F1117")
        prim = style_cfg["primary"]
        sec = style_cfg["secondary"]
        tert = style_cfg["tertiary"]
        accent = style_cfg["accent"]
        text_col = style_cfg["text"]
        style_name = style_cfg["name"]
        style_guidance = style_cfg["visual_guidance"]
        style_embellishments = style_cfg.get("svg_embellishments", "")

        archetype_info = detect_layout_archetype(topic, caption, panel_num, prim, sec, tert, card_bg=card_bg, sub_bg=sub_bg, text_col=text_col)
        archetype_name = archetype_info["archetype_name"]
        layout_guidance = archetype_info["layout_instructions"]

        prompt = f"""You are a world-class visual explainer and infographic designer (like Kurzgesagt or Vox).
Your goal is to explain this concept visually with PERFECT geometric alignment, zero text collisions, and complete concept accuracy in the requested aesthetic.

TOPIC: {topic}
PANEL {panel_num} OF 3: {caption}
DOMAIN: {domain_name}
LAYOUT ARCHETYPE: {archetype_name}
AESTHETIC STYLE: {style_name}
STYLE DESIGN GUIDANCE: {style_guidance}

STYLE VISUAL PALETTE & THEME:
- Canvas Background: {bg_color}
- Container Card Fill: {card_bg}
- Secondary / Inset Box Fill: {sub_bg}
- Primary Accent & Borders: {prim}
- Secondary Accent: {sec}
- Tertiary Accent: {tert}
- Main Text Color: {text_col}
- Highlight Accent: {accent}

MANDATORY STYLE VISUAL EMBELLISHMENTS:
{style_embellishments}

MANDATORY DESIGN & ALIGNMENT RULES:
1. TOPIC-ACCURATE CONCEPT MAPPING:
   - Your illustration MUST faithfully represent the specific details of:
     "{caption}"
   - If the caption mentions "three estates", "3 states", or 3 entities, you MUST draw all 3 distinct cards/tiers. Do NOT merge them!
   - Draw recognizable real-world icons fitting the "{domain_name}" domain, rendered according to the {style_name} aesthetic.
2. ZERO TEXT OVERLAPS (SPATIAL SEPARATION):
   - Icon coordinates and Text coordinates must NEVER be the same.
   - Text must be placed in a dedicated slot (inside a label pill or with >= 25px clear vertical offset).
   - NEVER place text inside an icon silhouette or path.
   - NO GHOST TEXT: Output exactly ONE clean <text> tag per label. NEVER duplicate a label with opacity="0.15".
3. NO FLOATING ORPHANS:
   - Every icon or sub-element must be visually enclosed in its parent container card or centered in the scene.
   - No floating badges in random corners.
4. VISUAL FIRST, MINIMAL WORDS:
   - Maximum 3 to 5 simple, friendly words per badge. No dense sentences or math formulas.
5. MODERN, BALANCED TYPOGRAPHY (ZERO CHUNKY FONTS):
   - Font Family: Use clean modern system sans-serif: font-family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" (or monospace font-family="'SF Mono', 'Courier New', monospace" for code/technical blueprints).
   - Font Weights: Use font-weight="600" for titles and badges. Use font-weight="400" or "500" for secondary labels and descriptions.
   - STRICTLY FORBIDDEN: NEVER use "Impact", "Arial Black", and NEVER use font-weight="900" or font-weight="800". All typography must look modern, balanced, refined, and readable.
6. CANVAS SPECIFICATIONS:
   - Root: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
   - Background: <rect width="800" height="800" fill="{bg_color}"/>
   - Palette: Primary Accent: {prim}, Secondary Accent: {sec}, Tertiary Accent: {tert}, Text: {text_col}, Highlight: {accent}.
   - Header: Simple badge ("STEP {panel_num}") and clean short title (2-4 words max).

{layout_guidance}

{guidance}

STRICT XML FORMAT:
- Return ONLY raw valid XML <svg>...</svg>. No markdown backticks, no code fences.
- Every ampersand must be written as &amp;.
"""
        response = invoke_llm_with_retry(prompt)
        raw = "".join([b["text"] for b in response.content if isinstance(b, dict) and b.get("type") == "text"]) if isinstance(response.content, list) else str(response.content)
        svg_content = sanitize_and_validate_svg(raw, topic, panel_num, caption, style=style)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"[SVG] Panel {panel_num} saved successfully ({len(svg_content)} bytes). Valid XML verified.", flush=True)
        return True
    except Exception as e:
        print(f"[SVG] Failed to generate SVG for panel {panel_num}: {e}. Writing emergency fallback...", flush=True)
        fallback_svg = build_fallback_svg(topic, panel_num, caption, style=style)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(fallback_svg)
        return True

STYLE_SUFFIX = STYLE_CONFIGS["comic"]["diffusion_suffix"]
GROUNDING_THRESHOLD = 1.0

LINKEDIN_CLIENT_ID = os.environ["LINKEDIN_CLIENT_ID"]
LINKEDIN_CLIENT_SECRET = os.environ["LINKEDIN_CLIENT_SECRET"]
LINKEDIN_REDIRECT_URI = "http://localhost:8000/auth/linkedin/callback"

# Temporary in-memory storage for the demo — good enough for a single-user project,
# not meant to scale to multiple real users.
LINKEDIN_SESSION_FILE = "data/linkedin_session.json"

def load_linkedin_session():
    if os.path.exists(LINKEDIN_SESSION_FILE):
        try:
            with open(LINKEDIN_SESSION_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"access_token": None, "person_urn": None, "name": None}

def save_linkedin_session(data):
    try:
        os.makedirs("data", exist_ok=True)
        with open(LINKEDIN_SESSION_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error persisting linkedin session: {e}", flush=True)

linkedin_session = load_linkedin_session()


class TopicRequest(BaseModel):
    topic: str
    audience: Optional[str] = "college"
    style: Optional[str] = "comic" 


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
        save_linkedin_session(linkedin_session)

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
    print(f"[LinkedIn Post] Initiating post for panel {panel_number}...", flush=True)
    if not linkedin_session["access_token"]:
        print("[LinkedIn Post] Error: Not connected to LinkedIn yet.", flush=True)
        return {"success": False, "message": "Not connected to LinkedIn yet. Please connect your LinkedIn account first."}

    access_token = linkedin_session["access_token"]
    person_urn = linkedin_session["person_urn"]
    image_path = f"data/images/panel_{panel_number}.png"
    svg_path = f"data/images/panel_{panel_number}.svg"

    # Auto-rasterize SVG to PNG if PNG doesn't exist
    if not os.path.exists(image_path) and os.path.exists(svg_path):
        print(f"[LinkedIn Post] Auto-rasterizing {svg_path} -> {image_path}...", flush=True)
        convert_svg_to_png(svg_path, image_path)

    # Fallback card if neither exists
    if not os.path.exists(image_path):
        print(f"[LinkedIn Post] Generating editorial card for panel {panel_number}...", flush=True)
        create_fallback_card("Explained", panel_number, caption, image_path)

    if not os.path.exists(image_path):
        print(f"[LinkedIn Post] Error: Image file could not be prepared for panel {panel_number}.", flush=True)
        return {"success": False, "message": f"No image found for panel {panel_number}."}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient() as client:
        # Step 1: Register Upload
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
            print(f"[LinkedIn Post] Failed to register upload: {register_data}", flush=True)
            return {"success": False, "message": "Failed to register upload with LinkedIn", "details": register_data}

        upload_url = register_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset_urn = register_data["value"]["asset"]

        # Step 2: Upload Binary Image
        with open(image_path, "rb") as img_file:
            image_bytes = img_file.read()

        upload_response = await client.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "image/png"
            },
            content=image_bytes,
        )

        if upload_response.status_code not in (200, 201):
            print(f"[LinkedIn Post] Media upload failed: HTTP {upload_response.status_code} {upload_response.text}", flush=True)
            return {"success": False, "message": "Image upload to LinkedIn failed", "status": upload_response.status_code}

        # Step 3: Create UGC Post
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
            print(f"[LinkedIn Post] UGC Post creation failed: HTTP {post_response.status_code} {post_response.text}", flush=True)
            return {"success": False, "message": "Post creation failed", "status": post_response.status_code, "details": post_response.text}

    print(f"[LinkedIn Post] Panel {panel_number} posted to LinkedIn successfully!", flush=True)
    return {"success": True, "message": "Posted to LinkedIn successfully."}



@app.post("/linkedin/post-carousel")
async def post_carousel_to_linkedin(
    file: UploadFile = File(...),
    commentary: str = Form(""),
    title: str = Form("ExplainIT Visual Carousel")
):
    print(f"[LinkedIn Carousel] Initiating carousel post: '{title}'...", flush=True)
    if not linkedin_session.get("access_token") or not linkedin_session.get("person_urn"):
        print("[LinkedIn Carousel] Error: Not connected to LinkedIn.", flush=True)
        return {"success": False, "message": "Not connected to LinkedIn yet. Please connect your LinkedIn account first."}

    access_token = linkedin_session["access_token"]
    person_urn = linkedin_session["person_urn"]

    pdf_bytes = await file.read()
    if not pdf_bytes or len(pdf_bytes) < 100:
        return {"success": False, "message": "Invalid or empty PDF document provided."}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Linkedin-Version": "202610",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Initialize Document Upload
        init_response = await client.post(
            "https://api.linkedin.com/rest/documents?action=initializeUpload",
            headers=headers,
            json={
                "initializeUploadRequest": {
                    "owner": person_urn
                }
            },
        )
        if init_response.status_code not in (200, 201):
            print(f"[LinkedIn Carousel] Init upload failed: {init_response.status_code} {init_response.text}", flush=True)
            return {"success": False, "message": "LinkedIn failed to initialize document upload.", "details": init_response.text}

        init_data = init_response.json()
        upload_val = init_data.get("value", {})
        upload_url = upload_val.get("uploadUrl")
        doc_urn = upload_val.get("document")

        if not upload_url or not doc_urn:
            return {"success": False, "message": "Malformed upload response from LinkedIn.", "details": init_data}

        # Step 2: Upload Binary PDF
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/pdf",
        }
        upload_response = await client.put(upload_url, headers=upload_headers, content=pdf_bytes)
        if upload_response.status_code not in (200, 201):
            print(f"[LinkedIn Carousel] Binary PDF upload failed: {upload_response.status_code} {upload_response.text}", flush=True)
            return {"success": False, "message": "Failed to upload document binary to LinkedIn.", "status": upload_response.status_code}

        # Step 3: Create Document Post
        clean_commentary = commentary.strip() if commentary else title
        post_payload = {
            "author": person_urn,
            "commentary": clean_commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "content": {
                "media": {
                    "id": doc_urn,
                    "title": title[:200]
                }
            },
            "lifecycleState": "PUBLISHED"
        }

        post_response = await client.post(
            "https://api.linkedin.com/rest/posts",
            headers=headers,
            json=post_payload,
        )

        if post_response.status_code not in (200, 201):
            print(f"[LinkedIn Carousel] Create post failed: {post_response.status_code} {post_response.text}", flush=True)
            return {"success": False, "message": "Failed to publish carousel post to LinkedIn feed.", "status": post_response.status_code, "details": post_response.text}

        post_urn = post_response.headers.get("x-restli-id", "")
        print(f"[LinkedIn Carousel] Successfully published carousel! Post URN: {post_urn}", flush=True)
        return {"success": True, "message": "Entire carousel published to LinkedIn successfully!", "post_urn": post_urn}



class LinkedInCopyRequest(BaseModel):
    topic: str
    panels: list = []
    audience: Optional[str] = "college"

@app.post("/generate-linkedin-copy")
def generate_linkedin_copy(request: LinkedInCopyRequest):
    topic = request.topic
    audience = (request.audience or "college").lower().strip()
    audience_cfg = AUDIENCE_CONFIGS.get(audience, AUDIENCE_CONFIGS["college"])
    panel_texts = "\n".join([f"Step {p.get('panel_number', i+1)}: {p.get('caption', '')}" for i, p in enumerate(request.panels)])
    
    prompt = f"""You are a top-tier educational LinkedIn creator.
Write a high-converting, viral LinkedIn post hook, key takeaways, and call-to-action for an illustrated carousel about:
TOPIC: {topic}

VOICE AND AUDIENCE: {audience_cfg['name']}
{audience_cfg['linkedin_prompt']}

PANEL STEPS:
{panel_texts}

REQUIREMENTS:
1. Hook: Engaging 1-2 sentence opening hook aligned with the {audience_cfg['name']} tone that stops the scroll.
2. Bullets: 3 concise, punchy bullet points summarizing the 3 steps with an emoji each.
3. CTA: Friendly call to action telling the reader to swipe through the carousel PDF and save the post.
4. Hashtags: 4-5 relevant industry/topic hashtags (including #ExplainIT).

Return ONLY valid JSON in this exact structure:
{{
  "hook": "Ever wondered how ...? Here is the 3-step visual breakdown: 👇",
  "takeaways": [
    "🔍 Step 1: ...",
    "⚙️ Step 2: ...",
    "✅ Step 3: ..."
  ],
  "cta": "Swipe through the carousel above 👆 for the full visual story! Save this post 📌 so you don't lose it.",
  "hashtags": ["#ExplainIT", "#VisualLearning", "#TechExplainer"]
}}
"""
    try:
        response = invoke_llm_with_retry(prompt)
        raw = response.content
        if isinstance(raw, list):
            raw = "".join([b["text"] for b in raw if isinstance(b, dict) and b.get("type") == "text"])
        cleaned = str(raw).strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)
        return data
    except Exception as e:
        print(f"[LinkedIn Copy] Fallback triggered: {e}", flush=True)
        return {
            "hook": f"Visual breakdown: How {topic} really works in 3 clear steps: 👇",
            "takeaways": [
                f"Step {p.get('panel_number', i+1)}: {p.get('caption', '')}" for i, p in enumerate(request.panels)
            ],
            "cta": "Swipe through the carousel above 👆 to see the full illustrated breakdown! Save 📌 and share with your network.",
            "hashtags": ["#ExplainIT", "#VisualLearning", "#Infographics", "#Education"]
        }




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
    audience = (request.audience or "college").lower().strip()
    if audience not in AUDIENCE_CONFIGS:
        audience = "college"
    style = (request.style or "comic").lower().strip()
    if style not in STYLE_CONFIGS:
        style = "comic"

    audience_cfg = AUDIENCE_CONFIGS[audience]
    style_cfg = STYLE_CONFIGS[style]

    vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)
    results_with_scores = vector_store.similarity_search_with_score(topic, k=4)

    if not results_with_scores or results_with_scores[0][1] > GROUNDING_THRESHOLD:
        return {
            "grounded": False,
            "message": f"Not enough grounded source material to explain '{topic}' yet. Try 'How GANs work'."
        }

    grounded_context = "\n\n".join([doc.page_content for doc, score in results_with_scores])

    prompt = f"""You are an expert educational infographic and visual storyteller.
Your mission is to generate a 3-panel visual explainer script for the topic: \"{topic}\".

AUDIENCE DEPTH GUIDANCE:
{audience_cfg['tone_prompt']}

AESTHETIC STYLE: {style_cfg['name']}

CONTEXT:
{grounded_context}

TOPIC TO EXPLAIN:
{topic}

PANEL SCRIPT REQUIREMENTS:
1. Strict Grounding: Use ONLY facts directly supported by the context above.
2. Audience Depth Adherence: The captions must strictly embody the {audience_cfg['name']} guidelines above.
3. Narrative Progression:
   - Panel 1: The Core Concept & Input (What is the starting point or problem?)
   - Panel 2: The Core Mechanism & Action (How does it work step-by-step?)
   - Panel 3: The Result & Grounded Output (What is the final accurate outcome?)
4. Caption: Clear, engaging, natural human explanation fitting {audience_cfg['name']} (1-2 sentences).

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
        try:
            panel_num = panel["panel_number"]
            caption = panel.get("caption", "")
            raw_prompt = panel.get("image_prompt") or panel.get("scene_description", "")
            image_prompt = raw_prompt.strip() + style_cfg["diffusion_suffix"]
            random_seed = random.randint(1, 1000000)
            encoded_prompt = quote(image_prompt)

            pollinations_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
            img_saved = False

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ExplainIT/1.0"
            }
            if pollinations_key:
                headers["Authorization"] = f"Bearer {pollinations_key}"
                image_gen_url = f"https://gen.pollinations.ai/image/{encoded_prompt}?key={pollinations_key}&width=1024&height=1024&seed={random_seed}&nologo=true"
            else:
                image_gen_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={random_seed}&nologo=true"

            print(f"[Generate] Attempting diffusion image for panel {panel_num} in '{style}' style...", flush=True)
            try:
                # 12-second fast attempt so IP rate-limiting doesn't hang the request
                img_response = requests.get(image_gen_url, headers=headers, timeout=12)
                if img_response.status_code == 200 and len(img_response.content) > 2000 and "image" in img_response.headers.get("content-type", ""):
                    png_path = f"data/images/panel_{panel_num}.png"
                    with open(png_path, "wb") as f:
                        f.write(img_response.content)
                    img_saved = True
                    print(f"[Generate] Diffusion image saved for panel {panel_num} ({len(img_response.content)} bytes).", flush=True)
                else:
                    print(f"[Generate] Diffusion skipped (status={img_response.status_code}); seamlessly switching to style-specific SVG synthesizer.", flush=True)
            except Exception as e:
                print(f"[Generate] Diffusion error/timeout for panel {panel_num}: {e}; seamlessly switching to style-specific SVG synthesizer.", flush=True)

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
                png_path = f"data/images/panel_{panel_num}.png"
                if generate_topic_svg(topic, panel_num, caption, svg_path, style=style):
                    panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.svg?t={cache_buster}"
                    convert_svg_to_png(svg_path, png_path)
                else:
                    fallback_svg = build_fallback_svg(topic, panel_num, caption, style=style)
                    with open(svg_path, "w", encoding="utf-8") as f:
                        f.write(fallback_svg)
                    panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.svg?t={cache_buster}"
                    convert_svg_to_png(svg_path, png_path)
            else:
                # Clean up stale svg counterpart if diffusion succeeded
                stale_svg = f"data/images/panel_{panel_num}.svg"
                if os.path.exists(stale_svg):
                    try:
                        os.remove(stale_svg)
                    except Exception:
                        pass
                panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png?t={cache_buster}"
        except Exception as e:
            print(f"[Generate] Emergency fallback in process_panel for panel {panel.get('panel_number')}: {e}", flush=True)
            panel_num = panel.get("panel_number", 1)
            caption = panel.get("caption", "")
            cache_buster = int(time.time() * 1000)
            svg_path = f"data/images/panel_{panel_num}.svg"
            png_path = f"data/images/panel_{panel_num}.png"
            fallback_svg = build_fallback_svg(topic, panel_num, caption, style=style)
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(fallback_svg)
            convert_svg_to_png(svg_path, png_path)
            panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.svg?t={cache_buster}"
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
    script["audience"] = audience
    script["style"] = style
    return script


class QuizRequest(BaseModel):
    topic: str
    audience: Optional[str] = "college"

@app.post("/generate-quiz")
def generate_quiz(request: QuizRequest):
    topic = request.topic
    audience = (request.audience or "college").lower().strip()
    audience_cfg = AUDIENCE_CONFIGS.get(audience, AUDIENCE_CONFIGS["college"])

    vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)
    results_with_scores = vector_store.similarity_search_with_score(topic, k=4)

    if not results_with_scores or results_with_scores[0][1] > GROUNDING_THRESHOLD:
        raise HTTPException(status_code=400, detail="Not enough grounded source material.")

    grounded_context = "\n\n".join([doc.page_content for doc, score in results_with_scores])

    prompt = f"""You are an expert educator. Create a 3-question multiple-choice quiz about \"{topic}\" based ONLY on this context:
{grounded_context}

AUDIENCE LEVEL: {audience_cfg['name']}
{audience_cfg['quiz_prompt']}

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

    quiz_data["audience"] = audience
    return quiz_data
