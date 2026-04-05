# Skill File Routing & Swift Client Integration

## Complete End-To-End Implementation Guide

This document explains the production file pipeline for all Claude skills (docx, pptx, xlsx, pdf) and how to implement proper SwiftUI generation animations.

---

## **🔹 Full File Generation Pipeline**

```
┌──────────────────────────────────────────────────────────────┐
│                      USER REQUESTS FILE                     │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  1. SkillGateway executes registered skill via Claude API    │
│     ✅  Includes `files-api-2025-04-14` beta header         │
│     ✅  Activates skill container with code execution        │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  2. Skill runs inside Claude sandbox, generates file         │
│     ✅  Skill writes file to container filesystem            │
│     ✅  Files API automatically intercepts saved files       │
│     ✅  Returns `file_id` reference in response              │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  3. Backend extracts file references from response           │
│     ✅  `_extract_files()` scans all response blocks         │
│     ✅  Filters out internal stdout/logging when files exist │
│     ✅  Collects all { "file_id": "file_abc123" } entries    │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  4. Backend downloads raw file bytes from Claude             │
│     ✅  `download_files()` calls `client.beta.files.download()`
│     ✅  Reads full byte stream from Anthropic servers        │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  5. 3-Tier Persistent Storage                                 │
│     ✅  Memory Cache    →  instant O(1) reads                │
│     ✅  Railway Volume  →  disk persistence                  │
│     ✅  Supabase Storage →  permanent cross-deployment backup│
│     ✅  Returns permanent system file_id (UUID v4)           │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  6. Stream Event Emitted to Client                           │
│     ✅  `data-file_download` event sent over AI SDK stream   │
│     ✅  Contains download URL, filename, size, type          │
└─────────────────────────────────────┬────────────────────────┘
                                      │
┌─────────────────────────────────────▼────────────────────────┐
│  7. Swift Client Downloads Directly From Backend             │
│     ✅  Authenticated GET request to `/files/{file_id}/download`
│     ✅  Backend serves file directly (never proxies Claude)  │
└──────────────────────────────────────────────────────────────┘
```

---

## **🔹 Swift Client Implementation**

### ✅ Stream Event Handling
In your Swift stream parser, listen for this exact event:
```swift
// Event received at end of generation
{
  "type": "data-file_download",
  "data": {
    "type": "file_download",
    "file_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "Fund_Fact_Sheet_Q1_2026.docx",
    "download_url": "/files/550e8400-e29b-41d4-a716-446655440000/download",
    "file_type": "docx",
    "size_kb": 124.7,
    "tool_name": "skill:potomac-docx-skill"
  }
}
```

### ✅ SwiftUI Generation Animation Pattern

Implement this state machine for all skill operations:

```swift
enum GenerationPhase: Equatable {
    case idle
    case thinking         // Initial LLM processing
    case generating       // Skill is actively building file
    case finalizing       // Downloading & storing file
    case complete(FileDownload)
    case failed(Error)
}

class SkillGenerationViewModel: ObservableObject {
    @Published var phase: GenerationPhase = .idle
    @Published var progress: Double = 0
    
    // Animation phases mapped to stream events
    func handleStreamEvent(_ event: StreamEvent) {
        switch event.type {
        case "start":
            phase = .thinking
            progress = 0.15
            
        case "text-delta":
            phase = .generating
            progress = min(progress + 0.02, 0.85)
            
        case "data-file_download":
            phase = .finalizing
            progress = 0.9
            
            // Queue background download
            Task {
                if let file = try await downloadFile(event.data) {
                    await MainActor.run {
                        self.phase = .complete(file)
                        self.progress = 1.0
                    }
                }
            }
            
        case "finish":
            if case .generating = phase {
                progress = 1.0
            }
            
        case "error":
            phase = .failed(event.error)
        }
    }
}
```

### ✅ Animation States
| Phase | UI Animation |
|-------|--------------|
| **Thinking** | Pulsing loading indicator, "Analyzing request..." |
| **Generating** | Progress bar with smooth incremental animation, "Building document..." |
| **Finalizing** | Success animation playing, "Preparing download..." |
| **Complete** | File card appears with download icon, bounce animation |

---

## **🔹 Critical Implementation Rules**

1.  **Never parse stdout for files:**
    - When a skill produces files, all stdout from code execution is **intentionally suppressed**
    - Only the `data-file_download` event contains valid file information
    - Do not try to extract filenames or links from the text stream

2.  **Do not proxy Claude files:**
    - Always download files to your backend first
    - Claude `file_id` expires after 72 hours
    - Your system `file_id` is permanent

3.  **All skills use the exact same pipeline:**
    - potomac-docx-skill
    - potomac-pptx
    - potomac-xlsx
    - pdf
    - docx
    - pptx
    - xlsx
    - All future skills will automatically follow this pattern

4.  **Stream is safe to terminate:**
    - File download happens after the text stream completes
    - User can navigate away, close tab, or disconnect and the file will still be stored permanently
    - Files are available at `/files` endpoint immediately

---

## **🔹 Download Endpoint Specification**

```http
GET /files/{file_id}/download
Authorization: Bearer {user_token}
```

Returns:
- Correct Content-Type for file
- `Content-Disposition: attachment; filename="..."`
- Raw binary file bytes
- CORS headers enabled for Swift client

---

## **🔹 Supported File Types**

| Skill | File Type | MIME Type |
|-------|-----------|-----------|
| potomac-docx-skill | .docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| potomac-pptx | .pptx | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| potomac-xlsx | .xlsx | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| pdf | .pdf | `application/pdf` |
| All other skills follow standard MIME types |

---

## **🔹 Production Status**

✅ This entire pipeline is already fully implemented in production  
✅ All existing skills already work this way  
✅ No backend changes required for new skills  
✅ Swift client only needs to implement the `data-file_download` event handler  
✅ Files are automatically persisted forever