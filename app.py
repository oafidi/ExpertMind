from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv
import os
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from src.pdf_handler import get_pdf_text, get_text_chunks
from src.vectorstore_handler import get_vectorstore
from src.conversation_handler import get_conversation_chain
from src.database_handler import (
    init_db, add_document, get_document, get_all_documents,
    add_chat_message, get_chat_history, delete_document
)
from src.feedback_handler import (
    init_feedback_db, add_feedback, get_feedback_stats, add_note
)

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['VECTORSTORE_DIR'] = 'vectorstores'

# Initialize the databases
init_db()
init_feedback_db()

# In-memory cache for loaded vector stores to avoid disk I/O on every request
vectorstore_cache = {}

def get_vectorstore_from_path(path):
    """Loads a vector store from the given path, caching it in memory."""
    if path in vectorstore_cache:
        return vectorstore_cache[path]
    
    try:
        # Allow dangerous deserialization as we are in control of the environment
        embeddings = OpenAIEmbeddings()
        vectorstore = FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
        vectorstore_cache[path] = vectorstore
        return vectorstore
    except Exception as e:
        print(f"Error loading vector store from {path}: {e}")
        return None

@app.route('/')
def index():
    files = get_all_documents()
    return render_template('index.html', files=files)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file selected'})
    
    filename = file.filename
    
    # Avoid processing if document already exists
    if get_document(filename):
        return jsonify({'filename': filename, 'message': 'File already exists.'})

    upload_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(upload_filepath)
    
    # Process the PDF and create vector store
    documents = get_pdf_text([upload_filepath])
    text_chunks = get_text_chunks(documents)
    vectorstore = get_vectorstore(text_chunks)
    
    # Save the vector store to disk
    vectorstore_path = os.path.join(app.config['VECTORSTORE_DIR'], filename)
    vectorstore.save_local(vectorstore_path)
    
    # Add document to the database
    add_document(filename, vectorstore_path)
    
    return jsonify({'filename': filename})

@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'})
    
    filename = data.get('filename')
    user_question = data.get('question', '').strip()
    
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': 'Please select a valid PDF.'})
    if not user_question:
        return jsonify({'error': 'Question cannot be empty.'})
        
    doc_id, vectorstore_path = doc_info
    vectorstore = get_vectorstore_from_path(vectorstore_path)
    if not vectorstore:
        return jsonify({'error': 'Could not load document data. Please try re-uploading.'})

    # Get learned context from feedback
    from src.feedback_handler import get_learned_context
    lc_used, learned_context = get_learned_context(doc_id, user_question)
    
    # Prepare learned context section for the prompt
    if lc_used and learned_context and learned_context.strip():
        learned_context_section = f"""
LEARNED KNOWLEDGE (High Priority):
The following information has been verified and enhanced through user feedback:

{learned_context}

INSTRUCTIONS:
1. Use the LEARNED KNOWLEDGE above as your PRIMARY reference
2. If the current question is similar to any learned patterns, prioritize that knowledge
3. Only use the regular context below to support or extend the learned knowledge
4. If learned knowledge contains corrections or enhancements, you MUST incorporate them
================================================================================================
"""
    else:
        learned_context_section = ""
    
    chain = get_conversation_chain(vectorstore, doc_id, learned_context_section)
    history = get_chat_history(doc_id)
    
    # Invoke the chain with the learned context section
    response = chain.invoke({
        "query": user_question, 
        "learned_context_section": learned_context_section
    })
        
    # Extract the answer and format it
    answer = response.get('result', 'Sorry, I could not find an answer.')
    
    # Check if this came from learned knowledge
    is_from_learned = learned_context and learned_context.strip()
    
    # Extract source page number
    source_page = None
    if response.get('source_documents'):
        first_doc = response['source_documents'][0]
        if hasattr(first_doc, 'metadata') and 'page' in first_doc.metadata:
            source_page = first_doc.metadata['page'] + 1

    # Save conversation to DB
    add_chat_message(doc_id, 'user', user_question)
    add_chat_message(doc_id, 'assistant', answer)
    
    return jsonify({
        'answer': answer, 
        'source_page': source_page,
        'is_from_learned': is_from_learned
    })

@app.route('/history', methods=['GET'])
def get_history():
    filename = request.args.get('filename')
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'history': []})
    
    doc_id, _ = doc_info
    history = get_chat_history(doc_id)
    return jsonify({'history': history})

@app.route('/feedback', methods=['POST'])
def submit_feedback():
    """Submit feedback for an answer"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'}), 400
    
    filename = data.get('filename')
    question = data.get('question')
    answer = data.get('answer')
    feedback_type = data.get('feedback_type')  # 'like' or 'dislike'
    additional_info = data.get('additional_info', '')
    
    if not all([filename, question, answer, feedback_type]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if feedback_type not in ['like', 'dislike']:
        return jsonify({'error': 'Invalid feedback type'}), 400
    
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': 'Document not found'}), 404
    
    doc_id, _ = doc_info
    
    try:
        success = add_feedback(doc_id, question, answer, feedback_type, additional_info)
        if success:
            return jsonify({'message': 'Feedback submitted successfully'})
        else:
            return jsonify({'error': 'Failed to submit feedback'}), 500
    except Exception as e:
        return jsonify({'error': f'Error submitting feedback: {str(e)}'}), 500

@app.route('/feedback/stats', methods=['GET'])
def get_feedback_statistics():
    """Get feedback statistics for a document"""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename parameter required'}), 400
    
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': 'Document not found'}), 404
    
    doc_id, _ = doc_info
    
    try:
        stats = get_feedback_stats(doc_id)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': f'Error getting stats: {str(e)}'}), 500

@app.route('/note', methods=['POST'])
def add_note_endpoint():
    """Add a detailed note for an answer"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'}), 400
    
    filename = data.get('filename')
    question = data.get('question')
    answer = data.get('answer')
    note_content = data.get('note_content')
    note_type = data.get('note_type', 'enhancement')
    
    if not all([filename, question, answer, note_content]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    valid_note_types = ['enhancement', 'clarification', 'correction', 'context', 'example']
    if note_type not in valid_note_types:
        return jsonify({'error': f'Invalid note type. Must be one of: {", ".join(valid_note_types)}'}), 400
    
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': 'Document not found'}), 404
    
    doc_id, _ = doc_info
    
    try:
        success = add_note(doc_id, question, answer, note_content, note_type)
        if success:
            return jsonify({
                'message': f'{note_type.title()} note added successfully',
                'note_type': note_type,
                'content': note_content
            })
        else:
            return jsonify({'error': 'Failed to add note'}), 500
    except Exception as e:
        return jsonify({'error': f'Error adding note: {str(e)}'}), 500

@app.route('/learned', methods=['GET'])
def get_learned_knowledge():
    """Get learned knowledge for a document"""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename parameter required'}), 400
    
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': 'Document not found'}), 404
    
    doc_id, _ = doc_info
    
    try:
        from src.feedback_handler import export_learned_knowledge
        learned_data = export_learned_knowledge(doc_id)
        return jsonify({'learned_knowledge': learned_data})
    except Exception as e:
        return jsonify({'error': f'Error getting learned knowledge: {str(e)}'}), 500

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    """Clear chat history for a document"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'}), 400
    
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'Filename is required.'}), 400
        
    try:
        doc_info = get_document(filename)
        if not doc_info:
            return jsonify({'error': 'Document not found.'}), 404
        
        doc_id, _ = doc_info
        
        # Clear chat messages for this document
        from src.database_handler import clear_chat_history
        success = clear_chat_history(doc_id)
        
        if success:
            return jsonify({'success': f'Chat history cleared for {filename}'})
        else:
            return jsonify({'error': 'Failed to clear chat history'}), 500
            
    except Exception as e:
        print(f"Error clearing chat history: {e}")
        return jsonify({'error': f'Error clearing chat history: {str(e)}'}), 500

@app.route('/delete', methods=['POST'])
def delete():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'})
    
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'Filename is required.'})
        
    try:
        # Remove from vectorstore cache if present
        doc_info = get_document(filename)
        if doc_info:
            _, vectorstore_path = doc_info
            if vectorstore_path in vectorstore_cache:
                del vectorstore_cache[vectorstore_path]

        delete_document(filename)
        return jsonify({'success': f'Document {filename} deleted successfully.'})
    except Exception as e:
        print(f"Error deleting document: {e}")
        return jsonify({'error': f'Error deleting document: {str(e)}'}), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['VECTORSTORE_DIR'], exist_ok=True)
    app.run(debug=True)

