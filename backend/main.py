import os
import json
import requests
from urllib.parse import quote
from dotenv import load_dotenv
from fastapi import FastAPI
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
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.4)

STYLE_SUFFIX = ", premium digital comic book art, gorgeous stunning illustrations, vivid colors, rich cinematic lighting, masterpiece, highly detailed, expressive characters, distinct linework, 8k resolution, no blur, no text, no watermark"
# Placeholder — you MUST test and tune this before Sunday. See note below.
GROUNDING_THRESHOLD = 1.0


class TopicRequest(BaseModel):
    topic: str


@app.get("/")
def read_root():
    return {"status": "ExplainIT backend is alive"}


@app.post("/generate")
def generate_comic(request: TopicRequest):
    topic = request.topic

    # 1. Retrieve grounded facts, WITH similarity scores this time
    vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)
    results_with_scores = vector_store.similarity_search_with_score(topic, k=4)

    # 2. Grounding check — refuse to generate if the topic isn't actually covered
    #    by the source material, instead of letting the AI make something up.
    if not results_with_scores or results_with_scores[0][1] > GROUNDING_THRESHOLD:
        return {
            "grounded": False,
            "message": f"Not enough grounded source material to explain '{topic}' yet. Try 'How GANs work'."
        }

    grounded_context = "\n\n".join([doc.page_content for doc, score in results_with_scores])

    # 3. Generate the panel script
    prompt = f"""You are writing a short educational visual guide explaining a topic to a beginner.

Use ONLY the facts below. Do not add any information that is not directly supported by this context.

CONTEXT:
{grounded_context}

Write a 3-panel visual script explaining: {topic}

IMPORTANT for image generation: Each panel's `scene_description` MUST describe a beautiful, highly attractive, and conceptual illustration that perfectly represents the specific text of that panel. 
Do NOT force any recurring characters or mascots (like robots) into the scenes. Instead, focus on rich visual metaphors, cinematic environments, and clear subject matter that directly matches the educational content of the caption.

Every scene_description should describe a distinct, premium, and stunning visual.
Return ONLY valid JSON, no markdown formatting, no code fences, no extra text. Exactly this shape:

{{
  "panels": [
    {{
      "panel_number": 1,
      "caption": "short, simple explanation text for this panel, one or two sentences",
      "scene_description": "a highly detailed visual description of the attractive, conceptual image for this panel"
    }}
  ]
}}
"""
    response = llm.invoke(prompt)
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

    # 4. Generate an image for each panel — via Pollinations.ai, no key, no quota
    os.makedirs("data/images", exist_ok=True)
    for panel in script["panels"]:
        panel_num = panel["panel_number"]
        image_prompt = panel["scene_description"] + STYLE_SUFFIX
        encoded_prompt = quote(image_prompt)
        image_gen_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&model=flux&seed=42&nologo=true"

        img_response = requests.get(image_gen_url, timeout=60)
        img_response.raise_for_status()

        output_path = f"data/images/panel_{panel_num}.png"
        with open(output_path, "wb") as f:
            f.write(img_response.content)

        panel["image_url"] = f"http://localhost:8000/images/panel_{panel_num}.png"

    script["grounded"] = True
    return script