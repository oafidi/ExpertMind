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
    
    # Create selected_document table to track currently chosen PDF
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS selected_document (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            document_id INTEGER,
            filename TEXT,
            selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    cursor.execute("SELECT id, filename, vectorstore_path FROM documents ORDER BY created_at DESC")
    results = cursor.fetchall()
    conn.close()
    return results

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

def set_selected_document(filename):
    """Set the currently selected document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get document info
    doc_info = get_document(filename)
    if not doc_info:
        conn.close()
        return False
    
    doc_id = doc_info[0]
    
    try:
        # Use INSERT OR REPLACE to ensure only one selected document exists
        cursor.execute('''
            INSERT OR REPLACE INTO selected_document (id, document_id, filename, selected_at) 
            VALUES (1, ?, ?, CURRENT_TIMESTAMP)
        ''', (doc_id, filename))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error setting selected document: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_selected_document():
    """Get the currently selected document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT sd.filename, sd.selected_at, d.vectorstore_path
        FROM selected_document sd
        JOIN documents d ON sd.document_id = d.id
        WHERE sd.id = 1
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'filename': result[0],
            'selected_at': result[1],
            'vectorstore_path': result[2]
        }
    return None

def clear_selected_document():
    """Clear the currently selected document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM selected_document WHERE id = 1')
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing selected document: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_all_feedback_with_documents():
    """Get all feedback with their associated document information."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            af.id,
            af.question,
            af.answer,
            af.feedback_type,
            af.additional_info,
            af.created_at,
            d.filename,
            d.id as document_id
        FROM answer_feedback af
        JOIN documents d ON af.document_id = d.id
        ORDER BY af.created_at DESC
    ''')
    
    results = cursor.fetchall()
    conn.close()
    
    feedback_list = []
    for row in results:
        feedback_list.append({
            'id': row[0],
            'question': row[1],
            'answer': row[2],
            'feedback_type': row[3],
            'additional_info': row[4],
            'created_at': row[5],
            'filename': row[6],
            'document_id': row[7]
        })
    
    return feedback_list
