#!/usr/bin/env python3
"""
Test script for the new feedback endpoints.
Run this after starting the Flask server with: python app.py
"""

import requests
import json
import sys

BASE_URL = "http://localhost:5001"

def test_endpoints():
    """Test the new feedback endpoints"""
    print("Testing PDF Feedback Endpoints...")
    print("=" * 50)
    
    try:
        # Test 1: Get all feedback
        print("\n1. Testing GET /all_feedback")
        response = requests.get(f"{BASE_URL}/all_feedback")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Found {len(data['feedback'])} feedback entries")
            print(f"📊 Summary: {data['summary']}")
            
            if data['by_document']:
                print(f"📄 Documents with feedback: {len(data['by_document'])}")
                for doc in data['by_document']:
                    print(f"   - {doc['filename']}: {doc['total_feedback']} feedback ({doc['likes']} likes, {doc['dislikes']} dislikes)")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
        
        # Test 2: Get feedback by document (if any documents exist)
        print("\n2. Testing GET /feedback_by_document")
        
        # First get all documents to see if any exist
        docs_response = requests.get(f"{BASE_URL}/")
        if docs_response.status_code == 200:
            # Try to get feedback for the first document with feedback
            if response.status_code == 200:
                data = response.json()
                if data['by_document']:
                    test_filename = data['by_document'][0]['filename']
                    print(f"Testing with document: {test_filename}")
                    
                    doc_feedback_response = requests.get(
                        f"{BASE_URL}/feedback_by_document", 
                        params={'filename': test_filename}
                    )
                    
                    if doc_feedback_response.status_code == 200:
                        doc_data = doc_feedback_response.json()
                        print(f"✅ Success! Document '{test_filename}' has {len(doc_data['feedback'])} feedback entries")
                        print(f"📊 Document Summary: {doc_data['summary']}")
                    else:
                        print(f"❌ Error: {doc_feedback_response.status_code} - {doc_feedback_response.text}")
                else:
                    print("ℹ️  No documents with feedback found")
            else:
                print("⚠️  Skipping document feedback test - no feedback data available")
        
        # Test 3: Get selected document
        print("\n3. Testing GET /selected_document")
        selected_response = requests.get(f"{BASE_URL}/selected_document")
        
        if selected_response.status_code == 200:
            selected_data = selected_response.json()
            if selected_data['has_selection']:
                print(f"✅ Currently selected document: {selected_data['selected_document']}")
                print(f"   Selected at: {selected_data['selected_at']}")
            else:
                print("ℹ️  No document currently selected")
        else:
            print(f"❌ Error: {selected_response.status_code} - {selected_response.text}")
        
        print("\n" + "=" * 50)
        print("✨ All tests completed!")
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the server.")
        print("💡 Make sure the Flask server is running with: python app.py")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_endpoints()
