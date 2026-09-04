from ingest import extract_text_from_file, build_vector_store
from langchain_huggingface import HuggingFaceEmbeddings

# Test with your existing GAN text file first — known-good content, isolates any bugs to the new code, not the data
with open("data/gan_source.txt", "rb") as f:
    file_bytes = f.read()

text = extract_text_from_file("gan_source.txt", file_bytes)
print(f"Extracted {len(text)} characters")
print(text[:200])
print("...\n")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
num_chunks = build_vector_store(text, embeddings)
print(f"Built vector store with {num_chunks} chunks")