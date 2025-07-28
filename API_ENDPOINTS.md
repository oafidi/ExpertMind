# PDF Selection and Feedback API Endpoints

This document describes the new endpoints added to the ExpertMind PDF Intelligence system.

## New Endpoints

### 1. Document Selection Endpoints

#### `POST /select_document`

Set the currently selected document.

**Request Body:**

```json
{
    "filename": "document.pdf"
}
```

**Response:**

```json
{
    "success": "Document document.pdf selected successfully.",
    "selected_document": "document.pdf"
}
```

#### `GET /selected_document`

Get the currently selected document.

**Response:**

```json
{
    "selected_document": "document.pdf",
    "selected_at": "2025-07-28 10:30:00",
    "has_selection": true
}
```

**Response (no selection):**

```json
{
    "selected_document": null,
    "selected_at": null,
    "has_selection": false,
    "message": "No document currently selected."
}
```

#### `POST /clear_selection`

Clear the currently selected document.

**Response:**

```json
{
    "success": "Document selection cleared successfully.",
    "selected_document": null
}
```

### 2. Feedback Endpoints

#### `GET /all_feedback`

Get all feedback with their associated documents and comprehensive statistics.

**Response:**

```json
{
    "feedback": [
        {
            "id": 1,
            "question": "What is the main topic?",
            "answer": "The document discusses...",
            "feedback_type": "like",
            "additional_info": "Very helpful explanation",
            "created_at": "2025-07-28 10:15:00",
            "filename": "document.pdf",
            "document_id": 1
        }
    ],
    "summary": {
        "total_feedback": 10,
        "total_likes": 7,
        "total_dislikes": 3,
        "satisfaction_rate": 70.0
    },
    "by_document": [
        {
            "filename": "document.pdf",
            "document_id": 1,
            "total_feedback": 5,
            "likes": 3,
            "dislikes": 2,
            "feedback_items": [...]
        }
    ]
}
```

#### `GET /feedback_by_document?filename=document.pdf`

Get feedback filtered by a specific document.

**Parameters:**

- `filename`: The name of the document to filter feedback for

**Response:**

```json
{
    "filename": "document.pdf",
    "document_id": 1,
    "feedback": [
        {
            "id": 1,
            "question": "What is the main topic?",
            "answer": "The document discusses...",
            "feedback_type": "like",
            "additional_info": "Very helpful explanation",
            "created_at": "2025-07-28 10:15:00",
            "filename": "document.pdf",
            "document_id": 1
        }
    ],
    "summary": {
        "total_feedback": 5,
        "likes": 3,
        "dislikes": 2,
        "satisfaction_rate": 60.0
    }
}
```

## Database Changes

### New Table: `selected_document`

Tracks the currently selected document for the user interface.

```sql
CREATE TABLE selected_document (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    document_id INTEGER,
    filename TEXT,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents (id)
);
```

### New Function: `get_all_feedback_with_documents()`

Joins feedback data with document information to provide comprehensive feedback reports.

## Features

### Automatic Selection Updates

- When a user asks a question and gets an answer, the document used for the answer is automatically set as the selected document
- This provides a seamless user experience where the interface tracks which PDF is currently being worked with

### Comprehensive Feedback Analytics

- Track user satisfaction rates across all documents
- View feedback trends by document
- Identify which documents provide the most helpful responses
- Monitor user engagement through feedback patterns

### Enhanced User Experience

- Users can explicitly select which PDF they want to work with
- Clear indicators of which document is currently active
- Easy access to feedback history for quality improvement

## Usage Examples

### Frontend Integration

```javascript
// Get currently selected document
fetch('/selected_document')
    .then(response => response.json())
    .then(data => {
        if (data.has_selection) {
            console.log('Current document:', data.selected_document);
        }
    });

// Select a document
fetch('/select_document', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({filename: 'my-document.pdf'})
});

// Get all feedback for analytics
fetch('/all_feedback')
    .then(response => response.json())
    .then(data => {
        console.log('Total feedback:', data.summary.total_feedback);
        console.log('Satisfaction rate:', data.summary.satisfaction_rate + '%');
    });
```

### Analytics Dashboard

The `/all_feedback` endpoint provides rich data for creating analytics dashboards:

- Overall satisfaction metrics
- Document-specific performance
- User engagement trends
- Quality improvement insights

## Testing

Run the test script to verify the endpoints:

```bash
python test_feedback_endpoints.py
```

Make sure the Flask server is running first:

```bash
python app.py
```
