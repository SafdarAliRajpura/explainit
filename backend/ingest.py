from pypdf import PdfReader
from io import BytesIO
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Pulls plain text out of an uploaded .txt or .pdf file."""
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
        return text.strip()
    elif filename.lower().endswith(".txt"):
        return file_bytes.decode("utf-8").strip()
    else:
        raise ValueError(f"Unsupported file type: {filename}. Only .txt and .pdf are allowed.")


def build_vector_store(text: str, embeddings, save_path: str = "data/faiss_index"):
    """Chunks the given text, embeds it, and saves it as the new active vector store.
    This REPLACES whatever document was previously grounded — single active document, by design."""
    if not text or len(text.strip()) < 50:
        raise ValueError("Extracted text is too short to build a meaningful knowledge base.")

    document = Document(page_content=text)
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
    chunks = splitter.split_documents([document])

    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(save_path)

    return len(chunks)