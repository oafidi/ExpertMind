# filepath: /home/ruined/Desktop/PDFBot/src/feedback_handler.py
import sqlite3
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
import numpy as np
import json

DB_PATH = 'pdf_intelligence.db'

def init_feedback_db():
    """Initialize feedback tables in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create feedback table for storing user feedback on answers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answer_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            feedback_type TEXT NOT NULL,  -- 'like', 'dislike'
            additional_info TEXT,         -- User's additional feedback/corrections
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    # Create learned knowledge table for storing improved answers with embeddings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learned_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            question_pattern TEXT NOT NULL,  -- Original question text
            question_embedding TEXT,         -- JSON stored vector embedding of the question
            improved_answer TEXT NOT NULL,   -- The answer that was liked + any additional info
            confidence_score REAL DEFAULT 1.0,  -- How much to trust this answer (increases with likes)
            usage_count INTEGER DEFAULT 0,      -- How many times this has been retrieved
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    # Create index for faster searches
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_learned_knowledge_doc_id 
        ON learned_knowledge(document_id)
    ''')
    
    conn.commit()
    conn.close()

def normalize_question(question: str) -> str:
    """Normalize question for better matching."""
    import re
    # Remove punctuation, convert to lowercase, remove extra spaces
    normalized = re.sub(r'[^\w\s]', '', question.lower())
    normalized = ' '.join(normalized.split())
    return normalized

def get_question_embedding(question: str) -> Optional[List[float]]:
    """Generate embedding for a question using OpenAI embeddings."""
    try:
        embeddings = OpenAIEmbeddings()
        embedding = embeddings.embed_query(question)
        return embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    try:
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm_vec1 = np.linalg.norm(vec1)
        norm_vec2 = np.linalg.norm(vec2)
        
        if norm_vec1 == 0 or norm_vec2 == 0:
            return 0.0
            
        return dot_product / (norm_vec1 * norm_vec2)
    except Exception as e:
        print(f"Error calculating cosine similarity: {e}")
        return 0.0

def add_feedback(document_id: int, question: str, answer: str, feedback_type: str, additional_info: str = None) -> bool:
    """Add user feedback for an answer."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Store the feedback
        cursor.execute('''
            INSERT INTO answer_feedback (document_id, question, answer, feedback_type, additional_info)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_id, question, answer, feedback_type, additional_info))
        
        # Process feedback for learned knowledge
        if feedback_type == 'like':
            # For likes, save the answer as-is (it's good as it is)
            _process_liked_answer(cursor, document_id, question, answer, additional_info)
        elif feedback_type == 'dislike':
            # For dislikes, we need improvement info to create better context
            if additional_info and additional_info.strip():
                _process_disliked_answer_with_improvement(cursor, document_id, question, answer, additional_info)
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error adding feedback: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def _process_liked_answer(cursor, document_id: int, question: str, answer: str, additional_info: str = None):
    """Process liked answer by saving it as verified knowledge."""
    question_pattern = normalize_question(question)
    
    # Generate embedding for the question
    question_embedding = get_question_embedding(question)
    question_embedding_json = json.dumps(question_embedding) if question_embedding else None
    
    # For liked answers, we save the original answer as the improved answer
    # Any additional info from user just adds extra context
    improved_answer = answer
    if additional_info and additional_info.strip():
        improved_answer = f"{answer}\n\n✨ User's Additional Context: {additional_info.strip()}"
    
    # Check if we already have learned knowledge for this question pattern
    cursor.execute('''
        SELECT id, confidence_score, improved_answer FROM learned_knowledge 
        WHERE document_id = ? AND question_pattern = ?
    ''', (document_id, question_pattern))
    
    existing = cursor.fetchone()
    
    if existing:
        # Update existing - increase confidence and potentially merge additional context
        learned_id, current_confidence, existing_answer = existing
        new_confidence = min(current_confidence + 0.3, 2.0)  # Bigger boost for likes
        
        # If there's new additional info, append it
        final_answer = existing_answer
        if additional_info and additional_info.strip():
            final_answer = f"{existing_answer}\n\n✨ Additional Context: {additional_info.strip()}"
        
        cursor.execute('''
            UPDATE learned_knowledge 
            SET improved_answer = ?, confidence_score = ?, question_embedding = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (final_answer, new_confidence, question_embedding_json, learned_id))
    else:
        # Create new learned knowledge entry with high confidence
        cursor.execute('''
            INSERT INTO learned_knowledge (document_id, question_pattern, question_embedding, improved_answer, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_id, question_pattern, question_embedding_json, improved_answer, 1.2))  # Higher starting confidence for likes

def _process_disliked_answer_with_improvement(cursor, document_id: int, question: str, answer: str, improvement_info: str):
    """Process disliked answer with user's improvement suggestions."""
    question_pattern = normalize_question(question)
    
    # Generate embedding for the question
    question_embedding = get_question_embedding(question)
    question_embedding_json = json.dumps(question_embedding) if question_embedding else None
    
    # Create improved answer based on user's feedback about what needs improvement
    # This becomes the new context for similar questions
    improved_answer = f"🔧 User suggested improvement: {improvement_info.strip()}"
    
    # Check if we already have learned knowledge for this question pattern
    cursor.execute('''
        SELECT id, confidence_score FROM learned_knowledge 
        WHERE document_id = ? AND question_pattern = ?
    ''', (document_id, question_pattern))
    
    existing = cursor.fetchone()
    
    if existing:
        # Update with improved answer based on user's correction
        learned_id, current_confidence = existing
        # Set moderate confidence since it's based on correction feedback
        new_confidence = 0.9
        
        cursor.execute('''
            UPDATE learned_knowledge 
            SET improved_answer = ?, confidence_score = ?, question_embedding = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (improved_answer, new_confidence, question_embedding_json, learned_id))
    else:
        # Create new learned knowledge entry with moderate confidence
        cursor.execute('''
            INSERT INTO learned_knowledge (document_id, question_pattern, question_embedding, improved_answer, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_id, question_pattern, question_embedding_json, improved_answer, 0.9))  # Good confidence since user provided improvement

def _process_note_feedback(cursor, document_id: int, question: str, answer: str, note_content: str, note_type: str):
    """Process detailed note feedback to enhance learned knowledge."""
    question_pattern = normalize_question(question)
    
    # Generate embedding for the question
    question_embedding = get_question_embedding(question)
    question_embedding_json = json.dumps(question_embedding) if question_embedding else None
    
    # Create enhanced answer based on note type
    if note_type == "enhancement":
        improved_answer = f"{answer}\n\n📝 User Enhancement: {note_content.strip()}"
    elif note_type == "clarification":
        improved_answer = f"{answer}\n\n🔍 Clarification: {note_content.strip()}"
    elif note_type == "correction":
        improved_answer = f"✅ Corrected Answer: {note_content.strip()}\n\n[Original answer: {answer}]"
    elif note_type == "context":
        improved_answer = f"{answer}\n\n🌐 Additional Context: {note_content.strip()}"
    elif note_type == "example":
        improved_answer = f"{answer}\n\n💡 Example: {note_content.strip()}"
    else:
        improved_answer = f"{answer}\n\n📋 Note ({note_type}): {note_content.strip()}"
    
    # Check if we already have learned knowledge for this question pattern
    cursor.execute('''
        SELECT id, confidence_score, improved_answer FROM learned_knowledge 
        WHERE document_id = ? AND question_pattern = ?
    ''', (document_id, question_pattern))
    
    existing = cursor.fetchone()
    
    if existing:
        # Append the note to existing knowledge
        learned_id, current_confidence, existing_answer = existing
        
        # Combine existing enhanced answer with new note
        combined_answer = f"{existing_answer}\n\n📋 Additional Note ({note_type}): {note_content.strip()}"
        
        # Increase confidence for helpful notes
        confidence_boost = 0.1 if note_type in ["enhancement", "clarification", "context", "example"] else 0.05
        new_confidence = min(current_confidence + confidence_boost, 2.0)
        
        cursor.execute('''
            UPDATE learned_knowledge 
            SET improved_answer = ?, confidence_score = ?, question_embedding = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (combined_answer, new_confidence, question_embedding_json, learned_id))
    else:
        # Create new learned knowledge entry
        initial_confidence = 1.0 if note_type in ["enhancement", "clarification"] else 0.8
        cursor.execute('''
            INSERT INTO learned_knowledge (document_id, question_pattern, question_embedding, improved_answer, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_id, question_pattern, question_embedding_json, improved_answer, initial_confidence))

def add_note(document_id: int, question: str, answer: str, note_content: str, note_type: str = "enhancement") -> bool:
    """Add a detailed note/annotation for an answer."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Store the note as feedback with special type
        cursor.execute('''
            INSERT INTO answer_feedback (document_id, question, answer, feedback_type, additional_info)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_id, question, answer, f"note_{note_type}", note_content))
        
        # Process the note to enhance learned knowledge
        _process_note_feedback(cursor, document_id, question, answer, note_content, note_type)
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error adding note: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_learned_context(document_id: int, question: str) -> str:
    """Get learned context using semantic similarity matching (RAG-like approach)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Generate embedding for the current question
        question_embedding = get_question_embedding(question)
        if not question_embedding:
            print("Failed to generate embedding for question")
            return False, ""
        
        # Get all learned knowledge for this document
        cursor.execute('''
            SELECT id, question_pattern, question_embedding, improved_answer, confidence_score, usage_count
            FROM learned_knowledge 
            WHERE document_id = ?
            ORDER BY confidence_score DESC
        ''', (document_id,))
        
        all_learned = cursor.fetchall()
        
        if not all_learned:
            return False, ""
        
        # Calculate semantic similarities
        similar_knowledge = []
        
        for learned_id, pattern, embedding_json, answer, confidence, usage_count in all_learned:
            if embedding_json:
                try:
                    stored_embedding = json.loads(embedding_json)
                    similarity = cosine_similarity(question_embedding, stored_embedding)
                    
                    # Consider it a match if similarity is above threshold
                    if similarity >= 0.75:  # High threshold for strong matches
                        similar_knowledge.append({
                            'id': learned_id,
                            'pattern': pattern,
                            'answer': answer,
                            'confidence': confidence,
                            'usage_count': usage_count,
                            'similarity': similarity,
                            'combined_score': similarity * confidence  # Weighted score
                        })
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Error parsing embedding for pattern '{pattern}': {e}")
                    continue
            else:
                # Fallback to keyword matching for entries without embeddings
                question_words = set(normalize_question(question).split())
                pattern_words = set(normalize_question(pattern).split())
                
                if question_words and pattern_words:
                    jaccard_similarity = len(question_words.intersection(pattern_words)) / len(question_words.union(pattern_words))
                    if jaccard_similarity >= 0.6:  # Lower threshold for keyword matching
                        similar_knowledge.append({
                            'id': learned_id,
                            'pattern': pattern,
                            'answer': answer,
                            'confidence': confidence,
                            'usage_count': usage_count,
                            'similarity': jaccard_similarity,
                            'combined_score': jaccard_similarity * confidence * 0.8  # Lower weight for keyword matching
                        })
        
        if not similar_knowledge:
            return False, ""
        
        # Sort by combined score (similarity * confidence)
        similar_knowledge.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # Update usage count for the best match
        best_match = similar_knowledge[0]
        cursor.execute('''
            UPDATE learned_knowledge 
            SET usage_count = usage_count + 1 
            WHERE id = ?
        ''', (best_match['id'],))
        conn.commit()
        
        # Build enhanced context string
        context_parts = []

        
        # Include top matches (limit to 3 for clarity)
        for i, match in enumerate(similar_knowledge[:3], 1):
            similarity_pct = match['similarity'] * 100
            match_strength = "VERY STRONG" if match['similarity'] >= 0.9 else "STRONG" if match['similarity'] >= 0.8 else "GOOD"
            
            context_parts.append(f"\n{i}. [{match_strength} MATCH - {similarity_pct:.1f}% similar]")
            context_parts.append(f"   Similar Question: '{match['pattern']}'")
            context_parts.append(f"   VERIFIED ANSWER (confidence: {match['confidence']:.2f}, used {match['usage_count']} times):")
            context_parts.append(f"   {match['answer']}")
            context_parts.append("-" * 80)
        context_parts.append("=" * 100)
        
        return True, "\n".join(context_parts)
        
    except Exception as e:
        print(f"Error in get_learned_context: {e}")
        return False, ""
    finally:
        conn.close()

def get_learned_answer(document_id: int, question: str) -> Optional[Dict[str, Any]]:
    """Get a learned answer for a question if one exists (kept for backward compatibility)."""
    context = get_learned_context(document_id, question)
    if context:
        # Extract the first answer from context for direct return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        question_pattern = normalize_question(question)
        
        try:
            cursor.execute('''
                SELECT improved_answer, confidence_score, usage_count
                FROM learned_knowledge 
                WHERE document_id = ? AND question_pattern = ?
                ORDER BY confidence_score DESC, updated_at DESC
                LIMIT 1
            ''', (document_id, question_pattern))
            
            result = cursor.fetchone()
            if result:
                improved_answer, confidence_score, usage_count = result
                return {
                    'answer': improved_answer,
                    'confidence': confidence_score,
                    'usage_count': usage_count,
                    'source': 'learned_knowledge'
                }
        except Exception as e:
            print(f"Error in get_learned_answer: {e}")
        finally:
            conn.close()
    
    return None

def create_learned_context_documents(document_id: int, question: str) -> List[Document]:
    """Create synthetic documents from learned knowledge to inject into retrieval."""
    learned_answer = get_learned_answer(document_id, question)
    
    if not learned_answer:
        return []
    
    # Create a high-priority document from learned knowledge
    learned_doc = Document(
        page_content=f"LEARNED KNOWLEDGE (High Confidence): {learned_answer['answer']}",
        metadata={
            'source': 'learned_knowledge',
            'confidence': learned_answer['confidence'],
            'usage_count': learned_answer['usage_count'],
            'page': 'learned',
            'priority': 'high'
        }
    )
    
    return [learned_doc]

def get_feedback_stats(document_id: int) -> Dict[str, Any]:
    """Get feedback statistics for a document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get total feedback counts
        cursor.execute('''
            SELECT feedback_type, COUNT(*) 
            FROM answer_feedback 
            WHERE document_id = ?
            GROUP BY feedback_type
        ''', (document_id,))
        
        feedback_counts = dict(cursor.fetchall())
        
        # Get learned knowledge count
        cursor.execute('''
            SELECT COUNT(*), AVG(confidence_score)
            FROM learned_knowledge 
            WHERE document_id = ?
        ''', (document_id,))
        
        learned_stats = cursor.fetchone()
        learned_count, avg_confidence = learned_stats if learned_stats else (0, 0)
        
        return {
            'total_likes': feedback_counts.get('like', 0),
            'total_dislikes': feedback_counts.get('dislike', 0),
            'learned_knowledge_count': learned_count or 0,
            'average_confidence': round(avg_confidence or 0, 2)
        }
        
    except Exception as e:
        print(f"Error getting feedback stats: {e}")
        return {}
    finally:
        conn.close()

def export_learned_knowledge(document_id: int) -> List[Dict[str, Any]]:
    """Export all learned knowledge for a document."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT question_pattern, improved_answer, confidence_score, usage_count, created_at, updated_at
            FROM learned_knowledge 
            WHERE document_id = ?
            ORDER BY confidence_score DESC, updated_at DESC
        ''', (document_id,))
        
        results = cursor.fetchall()
        
        learned_data = []
        for row in results:
            question_pattern, improved_answer, confidence_score, usage_count, created_at, updated_at = row
            learned_data.append({
                'question_pattern': question_pattern,
                'improved_answer': improved_answer,
                'confidence_score': confidence_score,
                'usage_count': usage_count,
                'created_at': created_at,
                'updated_at': updated_at
            })
        
        return learned_data
        
    except Exception as e:
        print(f"Error exporting learned knowledge: {e}")
        return []
    finally:
        conn.close()

