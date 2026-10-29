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

def generate_topic_svg(topic: str, panel_num: int, caption: str, output_path: str) -> bool:
    """
    Generates a bespoke, richly detailed, modern technical infographic SVG
    illustrating the exact mechanism and components of this panel.
    """
    print(f"[SVG] Generating SVG illustration for Panel {panel_num}...", flush=True)
    prompt = f"""You are an elite educational infographic designer and technical illustrator.
Create a rich, visually detailed, modern editorial SVG illustration for this explainer panel:
Topic: {topic}
Panel {panel_num} of 3: {caption}

DESIGN SYSTEM & SAFE BOUNDS SPECIFICATIONS:
- Root element: <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" width="100%" height="100%">
- Aesthetic: Premium dark-mode technical journal / editorial tech brand.
- Background: Base <rect width="800" height="800" fill="#15171A" rx="16"/> with subtle #262930 grid or structural framing.
- Accents: Vibrant amber (#E8A33D), cyan/blue (#38BDF8), emerald (#10B981) for key active nodes and glowing flows.
- SAFE DRAWING BOUNDARIES (CRITICAL TO AVOID CLIPPING):
  * Keep ALL visual elements, node boxes, text labels, arrows, and headers strictly inside a safe margin of at least 50px from all outer boundaries (i.e. x: 50 to 750, y: 50 to 750).
  * Absolutely NO text or shapes may bleed off or touch the outer border.
- STRUCTURE & LAYOUT:
  * Header zone (y: 60 to 115): Step label, e.g. "PANEL {panel_num} OF 3", and clear diagram title.
  * Diagram body (y: 135 to 680): Visually depict the EXACT mechanism, objects, data flow, and architecture described in the caption for "{topic}". Use labeled boxes, flowchart arrows, connecting pathways, glowing highlight rings, database cylinders, document cards, and transformer nodes matching this specific step.
  * Footer zone (y: 700 to 740): Clean status pill or component highlight badge.
- Typography: Clean, legible labels using system sans-serif fonts, with text colors #F2F1ED and #8B8D93.
- Return ONLY the raw valid <svg>...</svg> XML markup. No explanation, no markdown backticks, no code fences.
"""
    try:
        response = invoke_llm_with_retry(prompt)
        raw = "".join([b["text"] for b in response.content if isinstance(b, dict) and b.get("type") == "text"]) if isinstance(response.content, list) else str(response.content)
        svg = raw.strip()
        match = re.search(r'(<svg[\s\S]*?</svg>)', svg)
        if match:
            svg_content = match.group(1)
        else:
            svg_content = svg.replace('```xml', '').replace('```svg', '').replace('```', '').strip()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        print(f"[SVG] Panel {panel_num} SVG saved successfully ({len(svg_content)} bytes).", flush=True)
        return True
    except Exception as e:
        print(f"[SVG] Failed to generate SVG for panel {panel_num}: {e}", flush=True)
        return False

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

        if not img_saved:
            svg_path = f"data/images/panel_{panel_num}.svg"
            if generate_topic_svg(topic, panel_num, caption, svg_path):
                panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.svg"
            else:
                png_path = f"data/images/panel_{panel_num}.png"
                create_fallback_card(topic, panel_num, caption, png_path)
                panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png"
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
