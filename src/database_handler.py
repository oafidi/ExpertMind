import sqlite3
import os

DB_PATH = 'pdf_intelligence.db'
VECTORSTORE_DIR = 'vectorstores'

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            vectorstore_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create chat_messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_document(filename, vectorstore_path):
    """Adds a new document to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO documents (filename, vectorstore_path) VALUES (?, ?)",
            (filename, vectorstore_path)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Document with this filename already exists
        return get_document(filename)[0]
    finally:
        conn.close()

def get_document(filename):
    """Retrieves a document by its filename."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, vectorstore_path FROM documents WHERE filename = ?", (filename,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_all_documents():
    """Retrieves all documents from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM documents ORDER BY created_at DESC")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]

def add_chat_message(document_id, role, content):
    """Adds a chat message to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (document_id, role, content) VALUES (?, ?, ?)",
        (document_id, role, content)
    )
    conn.commit()
    conn.close()

def get_chat_history(document_id):
    """Retrieves the chat history for a given document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_messages WHERE document_id = ? ORDER BY created_at ASC",
        (document_id,)
    )
    results = cursor.fetchall()
    conn.close()
    # Format for LangChain MessagesPlaceholder
    return [{'role': role, 'content': content} for role, content in results]

def clear_chat_history(document_id: int) -> bool:
    """Clear all chat messages for a specific document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM chat_messages WHERE document_id = ?', (document_id,))
        conn.commit()
        deleted_count = cursor.rowcount
        print(f"Cleared {deleted_count} chat messages for document_id {document_id}")
        return True
    except Exception as e:
        print(f"Error clearing chat history: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_document(filename: str):
    """Delete a document and all associated data from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get the document ID and vectorstore path
    cursor.execute("SELECT id, vectorstore_path FROM documents WHERE filename = ?", (filename,))
    doc = cursor.fetchone()
    
    if doc:
        doc_id, vectorstore_path = doc[0], doc[1]
        
        # Delete associated chat messages
        cursor.execute("DELETE FROM chat_messages WHERE document_id = ?", (doc_id,))
        
        # Delete the document from DB
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        
        conn.commit()

        # Delete the vector store directory
        if vectorstore_path and os.path.exists(vectorstore_path):
            import shutil
            shutil.rmtree(vectorstore_path)
            
        # Delete the uploaded file
        upload_filepath = os.path.join('uploads', filename)
        if os.path.exists(upload_filepath):
            os.remove(upload_filepath)
    
    conn.close()
