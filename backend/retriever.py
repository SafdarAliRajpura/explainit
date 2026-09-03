from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

# Load the source document
loader = TextLoader("data/gan_source.txt")
documents = loader.load()

# Split it into smaller chunks so retrieval can pull just the relevant part
splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
chunks = splitter.split_documents(documents)
print(f"Split into {len(chunks)} chunks")

# Turn those chunks into embeddings and store them in FAISS
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = FAISS.from_documents(chunks, embeddings)

# Save it locally so we don't have to rebuild it every single run
vector_store.save_local("data/faiss_index")
print("Vector store built and saved.")

# Test: ask it something and see what it retrieves
query = "What is mode collapse?"
results = vector_store.similarity_search(query, k=2)

print(f"\nQuery: {query}")
for i, doc in enumerate(results):
    print(f"\n--- Result {i+1} ---")
    print(doc.page_content)