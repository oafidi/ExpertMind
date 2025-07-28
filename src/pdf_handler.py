from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

def get_pdf_text(pdf_docs):
    """Extracts text and metadata from a list of PDF documents."""
    documents = []
    for pdf_path in pdf_docs:
        pdf_reader = PdfReader(pdf_path)
        for page_num, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            if text:
                documents.append(Document(
                    page_content=text,
                    metadata={'source': pdf_path, 'page': page_num + 1}
                ))
    return documents

def get_text_chunks(documents):
    """Splits text into chunks for processing."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    chunks = text_splitter.split_documents(documents)
    return chunks
