from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

def get_vectorstore(documents):
    """Creates a FAISS vector store from a list of document chunks."""
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_documents(documents=documents, embedding=embeddings)
    return vectorstore
