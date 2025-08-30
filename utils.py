import PyPDF2
from docx import Document

def extract_text_from_pdf(file_path):
    """Extract text from PDF. For Word, use python-docx and adapt."""
    text = ""
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def extract_text_from_docx(file_path):
    doc = Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])

def extract_text(file_path):
    if file_path.endswith(".pdf"):
        return extract_text_from_pdf(file_path)
    elif file_path.endswith(".docx"):
        return extract_text_from_docx(file_path)
    return ""

def chunk_text(text, max_length=5000):
    """Chunk text for long documents to fit model context."""
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]