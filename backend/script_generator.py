import os
import json
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Load the vector store we built in retriever.py — no need to rebuild it
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = FAISS.load_local("data/faiss_index", embeddings, allow_dangerous_deserialization=True)

# Retrieve the facts we're grounding this comic in
topic = "How GANs work"
results = vector_store.similarity_search(topic, k=4)
grounded_context = "\n\n".join([doc.page_content for doc in results])

print("Retrieved context:")
print(grounded_context)
print("\n" + "="*50 + "\n")

# Set up Gemini
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.4)

prompt = f"""You are writing a short educational comic explaining a topic to a beginner.

Use ONLY the facts below. Do not add any information that is not directly supported by this context.

CONTEXT:
{grounded_context}

Write a 3-panel comic script explaining: {topic}

Return ONLY valid JSON, no markdown formatting, no code fences, no extra text. Exactly this shape:

{{
  "panels": [
    {{
      "panel_number": 1,
      "caption": "short, simple explanation text for this panel, one or two sentences",
      "scene_description": "a visual description of what should be illustrated in this panel, written for an image generation model"
    }}
  ]
}}
"""

response = llm.invoke(prompt)
raw_output = response.content

# Newer versions return content as a list of blocks instead of a plain string — unwrap it
if isinstance(raw_output, list):
    raw_output = "".join(
        block["text"] for block in raw_output
        if isinstance(block, dict) and block.get("type") == "text"
    )

print("Raw model output:")
print(raw_output)

# Parse it — models sometimes wrap JSON in markdown fences even when told not to
try:
    script = json.loads(raw_output)
except json.JSONDecodeError:
    cleaned = raw_output.strip().strip("```json").strip("```").strip()
    script = json.loads(cleaned)

# Save it — this file is exactly what the image generation step will read next
with open("data/panel_script.json", "w") as f:
    json.dump(script, f, indent=2)

print("\nPanel script saved to data/panel_script.json")
for panel in script["panels"]:
    print(f"\nPanel {panel['panel_number']}:")
    print(f"Caption: {panel['caption']}")
    print(f"Scene: {panel['scene_description']}")