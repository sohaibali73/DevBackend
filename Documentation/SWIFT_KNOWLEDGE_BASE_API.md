# Swift Client: Knowledge Base File API

## Complete Upload / Preview / Management Protocol

This document describes all endpoints and patterns for working with the backend knowledge base from Swift client.

---

## **🔹 Base API Path**
All endpoints are prefixed with:
```
/api/v1/knowledge/
```

All requests require standard Bearer token authentication.

---

## **🔹 1. Upload File To Knowledge Base**

### `POST /upload`
Upload a file to the knowledge base and trigger document processing.

**Request:**
```http
POST /api/v1/knowledge/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

[file binary data]
```

**Form Fields:**
| Field | Required | Description |
|-------|----------|-------------|
| `file` | ✅ | File binary data |
| `filename` | ✅ | Original filename |
| `document_type` | ❌ | `research`, `filing`, `internal`, `market_data` |
| `tags` | ❌ | Comma separated list |

**Response:**
```json
{
  "file_id": "doc_550e8400-e29b-41d4-a716-446655440000",
  "filename": "10-Q_Apple_Q1_2026.pdf",
  "file_type": "pdf",
  "size_kb": 2847.3,
  "status": "processing",
  "uploaded_at": 1743871200,
  "processing_progress": 0.0
}
```

✅ File will be automatically:
- OCR'd if scanned
- Chunked and vectorized
- Indexed for semantic search
- Available in chat context immediately

---

## **🔹 2. Check Processing Status**

### `GET /status/{file_id}`
Check processing status of uploaded file. Poll this endpoint every 500ms after upload.

**Response:**
```json
{
  "file_id": "doc_550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 0.67,
  "stage": "vectorizing",
  "total_pages": 84,
  "pages_processed": 56
}
```

**Status Values:**
| Status | Description |
|--------|-------------|
| `queued` | Waiting for processing |
| `parsing` | Extracting text / OCR |
| `vectorizing` | Generating embeddings |
| `indexing` | Adding to search index |
| `complete` | ✅ Ready for use |
| `failed` | Processing failed |

---

## **🔹 3. List All Knowledge Base Files**

### `GET /list`
Get paginated list of all files in knowledge base.

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `limit` | 50 | Results per page |
| `offset` | 0 | Pagination offset |
| `status` | all | Filter by status |
| `file_type` | all | Filter by file type |

**Response:**
```json
{
  "total": 147,
  "files": [
    {
      "file_id": "doc_abc123",
      "filename": "10-Q_Apple_Q1_2026.pdf",
      "file_type": "pdf",
      "size_kb": 2847.3,
      "status": "complete",
      "uploaded_at": 1743871200,
      "page_count": 84,
      "chunk_count": 312
    }
  ]
}
```

---

## **🔹 4. File Preview**

### `GET /preview/{file_id}`
Get file preview including extracted text and thumbnail.

**Response:**
```json
{
  "file_id": "doc_abc123",
  "filename": "10-Q_Apple_Q1_2026.pdf",
  "file_type": "pdf",
  "preview_text": "UNITED STATES SECURITIES AND EXCHANGE COMMISSION...",
  "page_count": 84,
  "thumbnail_url": "/api/v1/knowledge/thumbnail/doc_abc123",
  "download_url": "/api/v1/knowledge/download/doc_abc123",
  "extracted_text_available": true
}
```

---

## **🔹 5. Get Full Extracted Text**

### `GET /text/{file_id}`
Get full extracted plain text for document.

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `page` | all | Get specific page number |

Returns plain text response with correct encoding.

---

## **🔹 6. Get Thumbnail**

### `GET /thumbnail/{file_id}`
Get document thumbnail image.

**Query Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `size` | `medium` | `small` 128px, `medium` 256px, `large` 512px |
| `page` | 0 | Page number for multi-page documents |

Returns: `image/png` response

---

## **🔹 7. Download Original File**

### `GET /download/{file_id}`
Download original unmodified file.

Returns: Original file binary with correct Content-Type and Content-Disposition headers.

---

## **🔹 8. Delete File**

### `DELETE /{file_id}`
Delete file from knowledge base.

```http
DELETE /api/v1/knowledge/doc_abc123
Authorization: Bearer {token}
```

---

## **🔹 9. Search Knowledge Base**

### `POST /search`
Semantic search across all documents.

**Request Body:**
```json
{
  "query": "What was Apple's gross margin in Q1 2026?",
  "limit": 10,
  "file_filter": ["doc_abc123", "doc_def456"],
  "rerank": true
}
```

**Response:**
```json
{
  "results": [
    {
      "file_id": "doc_abc123",
      "filename": "10-Q_Apple_Q1_2026.pdf",
      "page": 17,
      "score": 0.947,
      "text": "Gross margin was 45.2% compared to 43.8% in the year-ago quarter...",
      "start_index": 14827,
      "end_index": 15142
    }
  ]
}
```

---

## **🔹 Swift Implementation Pattern**

```swift
class KnowledgeBaseService {
    static let shared = KnowledgeBaseService()
    
    func uploadFile(url: URL, progress: @escaping (Double) -> Void) async throws -> KBFile {
        // Implement multipart upload with progress tracking
    }
    
    func pollUntilComplete(fileId: String) async throws -> KBFile {
        // Poll status endpoint with exponential backoff
        var file: KBFile
        repeat {
            file = try await getStatus(fileId: fileId)
            try await Task.sleep(nanoseconds: 500_000_000)
        } while file.status == .queued || file.status == .processing
        return file
    }
    
    func search(query: String, limit: Int = 10) async throws -> [SearchResult] {
        // Semantic search request
    }
}
```

---

## **🔹 SwiftUI Components Checklist**

| Component | Purpose |
|-----------|---------|
| ✅ `FileUploadCard` | Upload progress, processing status, stages |
| ✅ `FileListCard` | Knowledge base browser with filtering |
| ✅ `FilePreviewCard` | Document preview with thumbnail and text |
| ✅ `DocumentReader` | Full document viewer with pages |
| ✅ `SearchResultRow` | Semantic search results with highlights |
| ✅ `SearchBar` | Knowledge base search interface |

---

## **🔹 Best Practices For Swift Client**

1.  **Upload Flow:**
    - Show upload progress bar
    - Show processing stages with animation
    - Do not block UI during processing
    - Auto-dismiss when complete

2.  **Search Flow:**
    - Debounce search input by 300ms
    - Show loading indicator during search
    - Highlight matching text in results
    - Link directly to document page

3.  **Caching:**
    - Cache thumbnails for 24 hours
    - Cache extracted text locally
    - Never cache search results

4.  **Error Handling:**
    - All endpoints can return 404 for deleted files
    - Processing failures should show retry button
    - Network errors should have automatic retry

---

## **🔹 Production Status**

✅ All endpoints are live in production  
✅ All file types supported: PDF, DOCX, XLSX, PPTX, TXT, CSV, PNG, JPG  
✅ OCR automatically enabled for scanned documents  
✅ Upload limits: 100MB per file, unlimited total storage  
✅ Documents are available in chat context automatically

This is the complete API for all knowledge base operations from Swift client.