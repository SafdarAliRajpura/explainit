import os
import time
import json
import random
import requests
import httpx
import urllib.parse
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/images", StaticFiles(directory="data/images"), name="images")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

def invoke_llm_with_retry(prompt: str, max_retries: int = 3):
    """
    Invokes Google Gemini with automatic retries, exponential backoff,
    and automatic fallback across models to handle 503 high-demand spikes.
    """
    candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash"]
    last_error = None

    for model_name in candidate_models:
        for attempt in range(max_retries):
            try:
                model = ChatGoogleGenerativeAI(model=model_name, temperature=0.4)
                return model.invoke(prompt)
            except Exception as e:
                last_error = e
                err_msg = str(e)
                # Check for transient capacity / demand spikes
                if any(code in err_msg for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]):
                    backoff = 2 * (attempt + 1)
                    print(f"[{model_name}] Transient error (attempt {attempt + 1}/{max_retries}): {e}. Waiting {backoff}s...")
                    time.sleep(backoff)
                else:
                    # Model not available or non-transient error, try next candidate model
                    print(f"[{model_name}] Encountered non-transient error: {e}. Switching to alternative model...")
                    break

    raise last_error

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

    prompt = f"""You are a clear, visually literate science communicator creating a grounded three-panel visual explainer.
    Write concise explanations and image directions for realistic editorial illustrations, not comic-book or fantasy art.

CONTEXT:
{grounded_context}

TOPIC TO EXPLAIN:
{topic}

PANEL SCRIPT REQUIREMENTS:
1. Grounding: Use ONLY facts directly supported by the context above.
2. Structure: Break down the explanation into 3 progressive panels:
   - Panel 1: The Core Concept / Setup
   - Panel 2: The Core Mechanism / Action / Conflict
   - Panel 3: The Result / Breakthrough / Impact
3. Caption: Clear, engaging, natural human tone (1-2 sentences).

IMAGE DIRECTION REQUIREMENTS:
1. Topic match: Every image_prompt must make the specific topic and that panel's point recognizable at a glance. Use the actual named entities, tools, materials, and actions from the topic, caption, and context; do not substitute unrelated stock metaphors or generic technology imagery.
2. Show the process: Depict the key subject performing the action described in the caption, and make important relationships or information flow visible using concrete objects and their arrangement.
3. Metaphors are optional: Prefer a direct, plausible depiction of the real process. Use a physical analogy only when it maps clearly to the process and does not replace or contradict the topic. Never force the same metaphor onto unrelated subjects.
4. Panel progression: Keep a coherent visual setting and subject across panels where appropriate, while changing the action/composition to show setup, mechanism, and outcome.
5. Specificity: Describe the main subject, its action, relevant topic-specific objects, setting, composition/camera angle, and lighting. Avoid vague descriptions that could illustrate many unrelated topics.
6. Style and exclusions: Use believable, realistic editorial illustration with natural-looking forms and materials. Avoid comic-book linework, fantasy, generic sci-fi corridors, glowing grids, floating numbers, robots, or holograms unless those elements are directly relevant to the topic and supported by context. Do not request readable text in the image.

For example, when explaining retrieval-augmented generation, a retrieval-stage image should visibly show a user's question being matched to relevant source documents and those selected passages being passed onward to a language model, if those steps are supported by the context. Do not depict an unrelated abstract data tunnel.

Return ONLY valid JSON with no markdown formatting and no code fences. Exactly this JSON schema:
{{
  "panels": [
    {{
      "panel_number": 1,
      "caption": "1-2 sentences clearly explaining the concept for this panel.",
      "image_prompt": "A realistic, specific scene that visibly represents this panel's topic and action, grounded in the caption and context."
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
    for panel in script["panels"]:
        panel_num = panel["panel_number"]
        # Use image_prompt if provided, fallback to scene_description
        raw_prompt = panel.get("image_prompt") or panel.get("scene_description", "")
        image_prompt = raw_prompt.strip() + STYLE_SUFFIX

        # Dynamic random seed per panel so images have distinct, fresh compositions
        random_seed = random.randint(1, 1000000)

        try:
            # Using POST is much more reliable than GET because it avoids URI Too Long (414) 
            # and complex URL encoding issues with long prompts.
            payload = {
                "prompt": image_prompt,
                "width": 1024,
                "height": 1024,
                "seed": random_seed,
                "nologo": True
            }
            headers = {"User-Agent": "ExplainIT/1.0"}
            
            img_response = requests.post("https://image.pollinations.ai/", json=payload, headers=headers, timeout=60)
            img_response.raise_for_status()

            output_path = f"data/images/panel_{panel_num}.png"
            with open(output_path, "wb") as f:
                f.write(img_response.content)

            panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png"
        except Exception as e:
            print(f"Error generating image for panel {panel_num}: {e}")
            # Ensure the frontend doesn't crash on connection error if image gen fails
            panel["image_url"] = f"https://placehold.co/1024x1024/0B0C0E/E8A33D.png?text=Generation+Failed"
        
        # Add delay between panel image generations to prevent rate limiting
        time.sleep(3.5)

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
