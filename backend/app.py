from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import os
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from src.pdf_handler import get_pdf_text, get_text_chunks
from src.vectorstore_handler import get_vectorstore
from src.conversation_handler import get_conversation_chain
from src.database_handler import (
    init_db, add_document, get_document, get_all_documents, retrieve_docs,
    add_chat_message, get_chat_history, delete_document,
    set_selected_document, get_selected_document, clear_selected_document,
    get_all_feedback_with_documents
)
from src.feedback_handler import (
    init_feedback_db, add_feedback, get_feedback_stats, add_note
)

load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
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

@app.route('/api/documents')
def index():
    files = retrieve_docs()
    selected_doc = get_selected_document()
    print(files)
    return jsonify({
        'files': files,
        'selected_document': selected_doc,
        'message': 'ExpertMind API is running'
    })

@app.route('/api/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/upload', methods=['POST'])
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

@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'})
    
    user_question = data.get('question', '').strip()
    if not user_question:
        return jsonify({'error': 'Question cannot be empty.'})

    all_docs = get_all_documents()
    if not all_docs:
        return jsonify({'error': 'No documents have been uploaded yet.'})

    best_doc_info = None
    highest_score = -1.0

    for doc_id, filename, vectorstore_path in all_docs:
        vectorstore = get_vectorstore_from_path(vectorstore_path)
        if vectorstore:
            try:
                # Perform similarity search
                results_with_scores = vectorstore.similarity_search_with_relevance_scores(user_question, k=1)
                if results_with_scores:
                    score = results_with_scores[0][1]
                    if score > highest_score:
                        highest_score = score
                        best_doc_info = {
                            "doc_id": doc_id,
                            "filename": filename,
                            "vectorstore": vectorstore
                        }
            except Exception as e:
                print(f"Could not perform similarity search on {filename}: {e}")
                continue
    
    if not best_doc_info:
        return jsonify({'error': 'Could not find a relevant document for your question.'})

    doc_id = best_doc_info['doc_id']
    vectorstore = best_doc_info['vectorstore']
    filename = best_doc_info['filename']
    
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
    
    # Invoke the chain with the learned context section
    response = chain.invoke({
        "query": user_question, 
        "learned_context_section": learned_context_section
    })
        
    # Extract the answer and format it
    answer = response.get('result', 'Sorry, I could not find an answer.')
    
    # Check if this came from learned knowledge
    is_from_learned = learned_context and learned_context.strip()
    
    # Extract source page number and content
    source_page = None
    source_content = None
    if response.get('source_documents'):
        first_doc = response['source_documents'][0]
        if hasattr(first_doc, 'metadata') and 'page' in first_doc.metadata:
            source_page = first_doc.metadata['page'] + 1
        if hasattr(first_doc, 'page_content'):
            source_content = first_doc.page_content

    # Save conversation to DB
    add_chat_message(doc_id, 'user', user_question)
    add_chat_message(doc_id, 'assistant', answer)
    
    # Update the selected document to the one that was used for answering
    set_selected_document(filename)
    
    return jsonify({
        'answer': answer, 
        'source_page': source_page,
        'source_content': source_content,
        'is_from_learned': is_from_learned,
        'filename': filename
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    filename = request.args.get('filename')
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'history': []})
    
    doc_id, _ = doc_info
    history = get_chat_history(doc_id)
    return jsonify({'history': history})

@app.route('/api/feedback', methods=['POST'])
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

@app.route('/api/feedback/stats', methods=['GET'])
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

@app.route('/api/note', methods=['POST'])
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

@app.route('/api/learned', methods=['GET'])
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

@app.route('/api/clear_chat', methods=['POST'])
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

@app.route('/api/delete', methods=['POST'])
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

@app.route('/api/select_document', methods=['POST'])
def select_document():
    """Set the currently selected document"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON input.'}), 400
    
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'Filename is required.'}), 400
    
    # Check if document exists
    doc_info = get_document(filename)
    if not doc_info:
        return jsonify({'error': f'Document {filename} not found.'}), 404
    
    try:
        success = set_selected_document(filename)
        if success:
            return jsonify({
                'success': f'Document {filename} selected successfully.',
                'selected_document': filename
            })
        else:
            return jsonify({'error': 'Failed to select document.'}), 500
    except Exception as e:
        print(f"Error selecting document: {e}")
        return jsonify({'error': f'Error selecting document: {str(e)}'}), 500

@app.route('/api/selected_document', methods=['GET'])
def get_selected_document_endpoint():
    """Get the currently selected document"""
    try:
        selected_doc = get_selected_document()
        if selected_doc:
            return jsonify({
                'selected_document': selected_doc['filename'],
                'selected_at': selected_doc['selected_at'],
                'has_selection': True
            })
        else:
            return jsonify({
                'selected_document': None,
                'selected_at': None,
                'has_selection': False,
                'message': 'No document currently selected.'
            })
    except Exception as e:
        print(f"Error getting selected document: {e}")
        return jsonify({'error': f'Error getting selected document: {str(e)}'}), 500

@app.route('/api/clear_selection', methods=['POST'])
def clear_selection():
    """Clear the currently selected document"""
    try:
        success = clear_selected_document()
        if success:
            return jsonify({
                'success': 'Document selection cleared successfully.',
                'selected_document': None
            })
        else:
            return jsonify({'error': 'Failed to clear document selection.'}), 500
    except Exception as e:
        print(f"Error clearing document selection: {e}")
        return jsonify({'error': f'Error clearing document selection: {str(e)}'}), 500

@app.route('/api/all_feedback', methods=['GET'])
def get_all_feedback():
    """Get all feedback with their associated documents"""
    try:
        feedback_list = get_all_feedback_with_documents()
        
        # Add summary statistics
        total_feedback = len(feedback_list)
        likes = sum(1 for f in feedback_list if f['feedback_type'] == 'like')
        dislikes = sum(1 for f in feedback_list if f['feedback_type'] == 'dislike')
        
        # Group by document for additional insights
        feedback_by_document = {}
        for feedback in feedback_list:
            filename = feedback['filename']
            if filename not in feedback_by_document:
                feedback_by_document[filename] = {
                    'filename': filename,
                    'document_id': feedback['document_id'],
                    'total_feedback': 0,
                    'likes': 0,
                    'dislikes': 0,
                    'feedback_items': []
                }
            
            feedback_by_document[filename]['total_feedback'] += 1
            feedback_by_document[filename]['feedback_items'].append(feedback)
            
            if feedback['feedback_type'] == 'like':
                feedback_by_document[filename]['likes'] += 1
            else:
                feedback_by_document[filename]['dislikes'] += 1
        
        return jsonify({
            'feedback': feedback_list,
            'summary': {
                'total_feedback': total_feedback,
                'total_likes': likes,
                'total_dislikes': dislikes,
                'satisfaction_rate': round((likes / total_feedback * 100), 2) if total_feedback > 0 else 0
            },
            'by_document': list(feedback_by_document.values())
        })
        
    except Exception as e:
        print(f"Error getting all feedback: {e}")
        return jsonify({'error': f'Error getting all feedback: {str(e)}'}), 500

@app.route('/api/feedback_by_document', methods=['GET'])
def get_feedback_by_document():
    """Get feedback filtered by document filename"""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename parameter is required'}), 400
    
    try:
        # Check if document exists
        doc_info = get_document(filename)
        if not doc_info:
            return jsonify({'error': f'Document {filename} not found'}), 404
        
        # Get all feedback and filter by the specific document
        all_feedback = get_all_feedback_with_documents()
        document_feedback = [f for f in all_feedback if f['filename'] == filename]
        
        # Calculate statistics for this document
        total_feedback = len(document_feedback)
        likes = sum(1 for f in document_feedback if f['feedback_type'] == 'like')
        dislikes = sum(1 for f in document_feedback if f['feedback_type'] == 'dislike')
        
        return jsonify({
            'filename': filename,
            'document_id': doc_info[0],
            'feedback': document_feedback,
            'summary': {
                'total_feedback': total_feedback,
                'likes': likes,
                'dislikes': dislikes,
                'satisfaction_rate': round((likes / total_feedback * 100), 2) if total_feedback > 0 else 0
            }
        })
        
    except Exception as e:
        print(f"Error getting feedback by document: {e}")
        return jsonify({'error': f'Error getting feedback by document: {str(e)}'}), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['VECTORSTORE_DIR'], exist_ok=True)
    app.run(debug=True, port=5000)

