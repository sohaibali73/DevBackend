# Analyst by Potomac - Complete API Guide

**Version:** 1.4.0  
**Base URL:** https://potomac-analyst-workbench-production.up.railway.app or http://localhost:8000  
**API Format:** RESTful JSON with streaming support  
**Authentication:** JWT Bearer token (Supabase Auth)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Core Endpoints](#core-endpoints)
3. [Chat & Conversation Routes](#chat--conversation-routes)
4. [AFL Generation Routes](#afl-generation-routes)
5. [Reverse Engineering Routes](#reverse-engineering-routes)
6. [AI/Vercel Integration Routes](#aivercel-integration-routes)
7. [Knowledge Base & Brain Routes](#knowledge-base--brain-routes)
8. [Analysis Routes](#analysis-routes)
9. [Content Management Routes](#content-management-routes)
10. [PowerPoint & Presentations Routes](#powerpoint--presentations-routes)
11. [Administrative Routes](#administrative-routes)
12. [Skills Routes](#skills-routes-apiskills)
13. [Unified File Download Routes](#unified-file-download-routes-files)
14. [Streaming Responses](#streaming-responses)

---

## Authentication

### Overview
All endpoints except `/`, `/health`, `/docs`, and `/openapi.json` require JWT authentication via Supabase Auth.

### Headers Required
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

### Rate Limiting
- **Limit:** 120 requests per minute per IP
- **Retry-After Header:** Included in 429 responses
- **Excluded:** `/health`, `/`, `/docs`, `/openapi.json`, `/routes`

---

## Core Endpoints

### Health Check
```
GET /health
```
Returns server status and router information.

**Response:**
```json
{
  "status": "healthy",
  "routers_active": 16,
  "routers_failed": 0
}
```

### Root Endpoint
```
GET /
```
Returns API metadata and loaded routers.

**Response:**
```json
{
  "name": "Analyst by Potomac API",
  "version": "1.3.7",
  "status": "online",
  "routers_loaded": ["auth", "chat", "afl", ...],
  "routers_failed": null
}
```

---

## Authentication Routes (`/auth`)

### Register User
```
POST /auth/register
```
Create a new user account with Supabase Auth.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepass123",
  "name": "John Doe"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user_id": "uuid",
  "email": "user@example.com",
  "expires_in": 3600
}
```

### Login
```
POST /auth/login
```
Authenticate and receive JWT token.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepass123"
}
```

**Response:** Same as register

### Get Current User
```
GET /auth/me
```
Get authenticated user's profile.

**Response:**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "nickname": "johndoe",
  "is_admin": false,
  "is_active": true,
  "has_api_keys": true,
  "created_at": "2024-01-01T00:00:00"
}
```

### Update Profile
```
PUT /auth/me
```
Update user profile and API keys.

**Request:**
```json
{
  "name": "Jane Doe",
  "nickname": "janedoe",
  "claude_api_key": "sk-...",
  "tavily_api_key": "tvly-..."
}
```

### Manage API Keys
```
PUT /auth/api-keys
GET /auth/api-keys
```
Update or check API key status (keys are encrypted before storage).

**Request (PUT):**
```json
{
  "claude_api_key": "sk-...",
  "tavily_api_key": "tvly-..."
}
```

**Response (GET):**
```json
{
  "has_claude_key": true,
  "has_tavily_key": true
}
```

### Password Management
```
POST /auth/forgot-password
POST /auth/reset-password
PUT /auth/change-password
POST /auth/refresh-token
POST /auth/logout
```

### Admin User Management
```
GET /auth/admin/users
POST /auth/admin/users/{user_id}/make-admin
POST /auth/admin/users/{user_id}/revoke-admin
POST /auth/admin/users/{user_id}/deactivate
POST /auth/admin/users/{user_id}/activate
```

---

## Chat & Conversation Routes (`/chat`)

### Get All Conversations
```
GET /chat/conversations
```
Fetch user's conversation list.

**Response:**
```json
[
  {
    "id": "uuid",
    "user_id": "uuid",
    "title": "AFL Strategy Discussion",
    "conversation_type": "agent",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-02T12:00:00"
  }
]
```

### Create Conversation
```
POST /chat/conversations
```

**Request:**
```json
{
  "title": "My Trading Strategy",
  "conversation_type": "agent"
}
```

### Send Message
```
POST /chat/message
```
Send message with Claude AI response and tool support.

**Request:**
```json
{
  "content": "Explain this AFL strategy",
  "conversation_id": "uuid"
}
```

**Response:**
```json
{
  "conversation_id": "uuid",
  "response": "AFL strategies use technical indicators...",
  "parts": [
    {"type": "text", "text": "Response text"},
    {"type": "tool-mermaid", "state": "output-available", "output": {...}}
  ],
  "tools_used": [{"tool": "web_search", "input": {...}, "result": {...}}],
  "all_artifacts": []
}
```

### Stream Message
```
POST /chat/stream
```
Stream response using Vercel AI SDK Data Stream Protocol.

**Same request as `/message` but returns `StreamingResponse`**

### Get Messages
```
GET /chat/conversations/{conversation_id}/messages
```
Fetch all messages in a conversation.

### Upload File to Conversation
```
POST /chat/conversations/{conversation_id}/upload
```
Upload file (CSV, PDF, PPTX, images) to conversation context.

**Request:**
```
Content-Type: multipart/form-data
file: <binary>
```

**Response:**
```json
{
  "file_id": "uuid",
  "filename": "data.csv",
  "template_id": "optional-pptx-template-id",
  "template_layouts": 10,
  "is_template": true
}
```

### Text-to-Speech
```
POST /chat/tts
GET /chat/tts/voices
```
Convert message to audio using edge-tts.

**Request (POST):**
```json
{
  "text": "This is the strategy...",
  "voice": "en-US-AriaNeural"
}
```

**Response:** MP3 audio stream

### Presentation Templates
```
POST /chat/template/upload
GET /chat/templates
```
Upload and manage PowerPoint templates.

### Download Presentation
```
GET /chat/presentation/{presentation_id}
```
Stream generated PowerPoint file.

### List Tools
```
GET /chat/tools
```
Get all available tools for chat agent.

### Update Conversation
```
PATCH /chat/conversations/{conversation_id}
```

**Request:**
```json
{
  "title": "Updated Title"
}
```

### Delete Conversation
```
DELETE /chat/conversations/{conversation_id}
```

---

## AFL Generation Routes (`/afl`)

### Generate AFL Code
```
POST /afl/generate
```
Generate AFL trading code from natural language description.

**Request:**
```json
{
  "prompt": "Create a RSI divergence strategy",
  "strategy_type": "standalone",
  "conversation_id": "uuid",
  "answers": {
    "strategy_type": "standalone",
    "trade_timing": "close"
  },
  "backtest_settings": {
    "initial_equity": 100000,
    "position_size": "100",
    "position_size_type": "spsPercentOfEquity",
    "max_positions": 10,
    "commission": 0.001,
    "trade_delays": [0, 0, 0, 0]
  },
  "stream": false
}
```

**Response:**
```json
{
  "code": "// AFL code here",
  "afl_code": "// AFL code here",
  "explanation": "This strategy...",
  "stats": {
    "quality_score": 85,
    "lines_of_code": 150
  }
}
```

### Optimize AFL Code
```
POST /afl/optimize
```

**Request:**
```json
{
  "code": "// AFL code to optimize"
}
```

### Debug AFL Code
```
POST /afl/debug
```

**Request:**
```json
{
  "code": "// AFL code",
  "error_message": "Compilation error..."
}
```

### Explain AFL Code
```
POST /afl/explain
```

**Request:**
```json
{
  "code": "// AFL code to explain"
}
```

**Response:**
```json
{
  "explanation": "This code calculates RSI..."
}
```

### Validate AFL Code
```
POST /afl/validate
```
Validate syntax without API call.

**Request:**
```json
{
  "code": "// AFL code"
}
```

**Response:**
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": []
}
```

### List User's AFL Codes
```
GET /afl/codes?limit=50
```

### Get Specific AFL Code
```
GET /afl/codes/{code_id}
```

### Delete AFL Code
```
DELETE /afl/codes/{code_id}
```

### AFL History
```
POST /afl/history
GET /afl/history?limit=50
DELETE /afl/history/{history_id}
```

### Upload Context Files
```
POST /afl/upload
GET /afl/files
GET /afl/files/{file_id}
DELETE /afl/files/{file_id}
```

### Settings Presets
```
POST /afl/settings/presets
GET /afl/settings/presets
GET /afl/settings/presets/{preset_id}
PUT /afl/settings/presets/{preset_id}
DELETE /afl/settings/presets/{preset_id}
POST /afl/settings/presets/{preset_id}/set-default
```

---

## Reverse Engineering Routes (`/reverse-engineer`)

### Start Reverse Engineering
```
POST /reverse-engineer/start
```
Begin new strategy reverse engineering session.

**Request:**
```json
{
  "query": "momentum-based trading strategy",
  "message": "alternative",
  "description": "alternative"
}
```

**Response:**
```json
{
  "strategy_id": "uuid",
  "conversation_id": "uuid",
  "phase": "clarification",
  "response": "I'll help you reverse engineer..."
}
```

### Continue Conversation
```
POST /reverse-engineer/continue
```

**Request:**
```json
{
  "strategy_id": "uuid",
  "strategyId": "uuid",
  "id": "uuid",
  "message": "Continue with more details",
  "content": "alternative"
}
```

### Conduct Research
```
POST /reverse-engineer/research/{strategy_id}
```
Run web research on the strategy.

**Response:**
```json
{
  "strategy_id": "uuid",
  "phase": "findings",
  "response": "Based on research, here are the key components..."
}
```

### Generate Schematic
```
POST /reverse-engineer/schematic/{strategy_id}
```
Create visual Mermaid diagram of strategy.

**Response:**
```json
{
  "strategy_id": "uuid",
  "phase": "schematic",
  "schematic": {
    "strategy_name": "...",
    "strategy_type": "momentum",
    "timeframe": "daily",
    "indicators": ["RSI", "MA"],
    "entry_logic": "RSI < 30 AND Price > MA",
    "exit_logic": "RSI > 70 OR Stop Loss"
  },
  "mermaid_diagram": "flowchart TD..."
}
```

### Generate Code from Strategy
```
POST /reverse-engineer/generate-code/{strategy_id}
```
Generate AFL code from reverse engineered strategy.

**Response:**
```json
{
  "strategy_id": "uuid",
  "phase": "coding",
  "code": "// AFL code",
  "response": "AFL strategy generated..."
}
```

### Get Strategy Details
```
GET /reverse-engineer/strategy/{strategy_id}
```

### Reverse Engineer History
```
POST /reverse-engineer/history
GET /reverse-engineer/history?limit=50
DELETE /reverse-engineer/history/{history_id}
```

---

## AI/Vercel Integration Routes (`/api/ai`)

### AI SDK Chat
```
POST /api/ai/chat
```
Direct Vercel AI SDK compatible endpoint for `useChat()` hook.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Generate a trading strategy"}
  ],
  "model": "claude-sonnet-4-20250514",
  "system": "You are a trading expert...",
  "max_tokens": 4096,
  "tools": [...],
  "stream": true,
  "conversation_id": "uuid",
  "include_kb": true
}
```

**Response:** Streaming Data Stream Protocol format

### Text Completion
```
POST /api/ai/completion
```
For `useCompletion()` hook.

**Request:**
```json
{
  "prompt": "Complete this strategy code:",
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 2048
}
```

### Generate UI Components
```
POST /api/ai/generate-ui
```
Generate React components, charts, diagrams.

**Request:**
```json
{
  "prompt": "Create a performance chart",
  "context": "Trading performance data",
  "component_type": "react"
}
```

### List Available Tools
```
GET /api/ai/tools
```

---

## Knowledge Base & Brain Routes (`/brain`)

### Upload Documents
```
POST /brain/upload
```
Upload trading documents, strategies, research.

### Search Knowledge Base
```
POST /brain/search
```
Search user's document collection.

**Request:**
```json
{
  "query": "momentum indicator",
  "limit": 10
}
```

### List Documents
```
GET /brain/documents
```

### Get Document Details
```
GET /brain/documents/{doc_id}
```

### Delete Document
```
DELETE /brain/documents/{doc_id}
```

### Generate Embeddings
```
POST /brain/embed
```
Create semantic embeddings for documents.

### Get Brain Stats
```
GET /brain/stats
```

---

## Analysis Routes

### Backtest Analysis (`/backtest`)

```
POST /backtest/analyze
```
Analyze backtest results using Claude.

**Request:**
```json
{
  "results": "Backtest results JSON...",
  "code": "AFL code..."
}
```

### Researcher (`/researcher`)

```
POST /researcher/analyze
```
Conduct company research.

```
GET /researcher/history
```
Get research history.

### Content Management (`/content`)

```
POST /content/articles
GET /content/articles
DELETE /content/articles/{id}
```

### Training & Feedback (`/train`)

```
POST /train/feedback
GET /train/feedback
```
Provide feedback to improve strategies.

### Health Diagnostics (`/health`)

```
GET /health/system
```
System health and database diagnostics.

### File Upload (`/upload`)

```
POST /upload/file
GET /upload/files
DELETE /upload/files/{file_id}
```

### Stock Data (`/yfinance`)

```
GET /yfinance/ticker/{symbol}
GET /yfinance/historical/{symbol}
GET /yfinance/options/{symbol}
```
Fetch real-time and historical stock data.

---

## PowerPoint & Presentations Routes

### PPTX Engine (`/pptx`)

```
POST /pptx/upload-image
```
Upload chart/image for slides.

```
POST /pptx/assemble
```
Assemble PPTX from slide plan.

```
GET /pptx/download/{filename}
```
Download generated file.

```
GET /pptx/templates
```
List available templates.

### PPTX Generation (`/pptx/generate`)

```
POST /pptx/generate
```
Full pipeline: Claude → Slide Plan → PPTX.

**Request:**
```json
{
  "brief": "Create investment presentation",
  "deck_family": "bull-bear",
  "uploaded_images": ["uuid"],
  "user_id": "uuid"
}
```

**Response:**
```json
{
  "download_url": "https://...",
  "slide_count": 12,
  "plan": {...},
  "filename": "presentation.pptx"
}
```

---

## Administrative Routes (`/admin`)

### System Health
```
GET /admin/health/system
```

### Database Diagnostics
```
GET /admin/health/database
```

### User Management
```
GET /admin/users
POST /admin/users/{user_id}/make-admin
POST /admin/users/{user_id}/revoke-admin
POST /admin/users/{user_id}/deactivate
POST /admin/users/{user_id}/activate
```

---

## Skills Routes (`/api/skills`)

Claude custom beta skills for document generation, presentations, research, AFL, quant analysis, and more. Skills use Claude's code execution sandbox to generate actual files (DOCX, PPTX).

### List All Skills
```
GET /api/skills
GET /api/skills?category=document
```
List all available skills, optionally filtered by category.

**Query Parameters:**
- `category` (optional): `afl`, `document`, `presentation`, `ui`, `backtest`, `market_analysis`, `quant`, `research`

**Response:**
```json
{
  "skills": [
    {
      "skill_id": "potomac-pptx",
      "name": "Potomac PPTX Skill",
      "slug": "potomac-pptx-skill",
      "description": "Create Potomac-branded PowerPoint presentations",
      "category": "presentation",
      "max_tokens": 16384,
      "tags": ["pptx", "presentations", "brand"],
      "enabled": true,
      "supports_streaming": true
    }
  ],
  "total": 9,
  "category_filter": null
}
```

### List Skill Categories
```
GET /api/skills/categories
```

**Response:**
```json
{
  "categories": [
    {"category": "document", "label": "Document", "count": 1},
    {"category": "presentation", "label": "Presentation", "count": 1},
    {"category": "research", "label": "Research", "count": 1}
  ]
}
```

### Get Skill Details
```
GET /api/skills/{slug}
```

### Execute Skill (Blocking JSON)
```
POST /api/skills/{slug}/execute
```
Execute a skill and return the full result as JSON. If the skill produces files (DOCX/PPTX), they are automatically downloaded from Claude's Files API, stored in the local file store, and download URLs are included in the response.

**Request:**
```json
{
  "message": "Create a Q1 2025 market outlook presentation with 10 slides",
  "system_prompt": null,
  "conversation_history": null,
  "max_tokens": null,
  "extra_context": "",
  "stream": false
}
```

**Response (with file artifacts):**
```json
{
  "text": "I've created your presentation...",
  "skill": "potomac-pptx-skill",
  "skill_name": "Potomac PPTX Skill",
  "usage": {"input_tokens": 1234, "output_tokens": 5678},
  "model": "claude-haiku-4-5-20251001",
  "execution_time": 45.2,
  "stop_reason": "end_turn",
  "files": [{"file_id": "file_abc123"}],
  "downloadable_files": [
    {
      "file_id": "file_abc123",
      "filename": "Q1_2025_Market_Outlook.pptx",
      "file_type": "pptx",
      "size_kb": 156.3,
      "download_url": "/files/file_abc123/download"
    }
  ],
  "download_url": "/files/file_abc123/download",
  "filename": "Q1_2025_Market_Outlook.pptx"
}
```

### Stream Skill (Vercel AI SDK Protocol)
```
POST /api/skills/{slug}/stream
POST /api/skills/{slug}/execute  (with "stream": true)
```
Stream a skill response using the Vercel AI SDK Data Stream Protocol. Compatible with `useChat()` / `useCompletion()` hooks.

When the skill produces file artifacts (DOCX/PPTX), the backend:
1. Extracts file IDs from the final streaming message
2. Downloads files from Claude's Files API
3. Stores them in the local file store
4. Emits `file_download` events via Data Stream Protocol type `2:` (custom data)

**Request:** Same as execute endpoint, body ignored for `/stream`.

**Streaming Response Format:**
```
0:"Here is your presentation..."
0:"I've created 10 slides covering..."
2:[{"type":"file_download","file_id":"file_abc123","filename":"presentation.pptx","download_url":"/files/file_abc123/download","file_type":"pptx","size_kb":156.3,"tool_name":"skill:potomac-pptx-skill"}]
d:{"finishReason":"stop","usage":{"promptTokens":1234,"completionTokens":5678},"skill":"potomac-pptx-skill","skillName":"Potomac PPTX Skill","executionTime":45.2}
```

**Frontend handling for file downloads in streaming:**
```typescript
await apiClient.streamSkill('potomac-pptx-skill', prompt, {
  onText: (text) => { /* append streamed text */ },
  onData: (data) => {
    // Handle file_download events
    const items = Array.isArray(data) ? data : [data];
    for (const item of items) {
      if (item?.type === 'file_download') {
        // Render a download card with item.download_url, item.filename, etc.
      }
    }
  },
  onFinish: (data) => { /* execution complete */ },
});
```

### Submit Background Skill Job
```
POST /api/skills/{slug}/job
```
Submit a skill to run in the background. Returns immediately with a `job_id`. Poll for results.

**Request:**
```json
{
  "message": "Create a fund fact sheet for XYZ Fund",
  "extra_context": ""
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "pending",
  "skill": "potomac-docx-skill",
  "skill_name": "Potomac DOCX Skill"
}
```

### Get Skill Job Status
```
GET /api/skills/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "uuid",
  "skill_slug": "potomac-docx-skill",
  "skill_name": "Potomac DOCX Skill",
  "message": "Create a fund fact sheet...",
  "status": "complete",
  "progress": 100,
  "status_message": "Done!",
  "result": {
    "text": "Document content...",
    "skill": "potomac-docx-skill",
    "execution_time": 32.5,
    "usage": {"input_tokens": 800, "output_tokens": 4500}
  },
  "error": null
}
```

### List Skill Jobs
```
GET /api/skills/jobs
```

### Execute Multiple Skills
```
POST /api/skills/multi
```

**Request:**
```json
{
  "requests": [
    {"skill_slug": "backtest-expert", "message": "Analyze this equity curve..."},
    {"skill_slug": "quant-analyst", "message": "Build a momentum factor..."}
  ]
}
```

---

## Unified File Download Routes (`/files`)

Unified file download system for all tool-generated and skill-generated files (DOCX, PPTX, PDF, CSV, etc.). Files are stored in an in-memory cache (2-hour TTL) with automatic fallback to Claude's Files API for skill-generated files.

### Download File
```
GET /files/{file_id}/download
GET /files/{file_id}/download?filename=custom_name.pptx
```
Download a generated file by its ID. The endpoint:
1. First checks the in-memory file store
2. Falls back to Claude's Files API (for skill-generated files with `file_` prefix)
3. Caches downloaded files locally for future requests

**Query Parameters:**
- `filename` (optional): Override the download filename

**Response:** Binary file with appropriate Content-Type and Content-Disposition headers.

**Supported MIME types:** `.docx`, `.pptx`, `.pdf`, `.csv`, `.xlsx`, `.json`, `.txt`, `.md`, `.png`, `.jpg`

### Get File Info
```
GET /files/{file_id}/info
```
Get file metadata without downloading.

**Response:**
```json
{
  "file_id": "file_abc123",
  "filename": "presentation.pptx",
  "file_type": "pptx",
  "size_kb": 156.3,
  "exists": true
}
```

### List Generated Files
```
GET /files/generated
```
List all currently available generated files in the in-memory store.

**Response:**
```json
{
  "files": [
    {
      "file_id": "file_abc123",
      "filename": "presentation.pptx",
      "file_type": "pptx",
      "size_kb": 156.3,
      "tool_name": "skill:potomac-pptx-skill",
      "download_url": "/files/file_abc123/download"
    }
  ]
}
```

---

## Error Handling

### Status Codes
- **200:** Success
- **201:** Created
- **400:** Bad Request
- **401:** Unauthorized
- **403:** Forbidden
- **404:** Not Found
- **429:** Rate Limited
- **500:** Server Error

### Error Response Format
```json
{
  "detail": "Error description",
  "type": "ErrorType"
}
```

---

## Streaming Responses

### Data Stream Protocol
Streaming endpoints (chat, completion, skills) use the Vercel AI SDK Data Stream Protocol.

**Format:** `{type_code}:{JSON_value}\n` where each line is a single event.

### Type Codes

| Code | Name | Description |
|------|------|-------------|
| `0` | Text Part | Streamed text delta: `0:"chunk of text"\n` |
| `2` | Data Part | Custom data (arrays): `2:[{...}]\n` — used for artifacts, metadata, and **file downloads** |
| `3` | Error Part | Error message: `3:"error description"\n` |
| `7` | Tool Call Start | Start of streaming tool call |
| `8` | Tool Call Delta | Tool call argument delta |
| `9` | Tool Call | Complete tool call: `9:{"toolCallId":"...","toolName":"...","args":{...}}\n` |
| `a` | Tool Result | Tool execution result: `a:{"toolCallId":"...","result":"..."}\n` |
| `d` | Finish Message | Stream complete: `d:{"finishReason":"stop","usage":{...}}\n` |
| `e` | Finish Step | Multi-step tool use step complete |
| `f` | Start Step | New step beginning |

### File Download Events (type `2:`)

When a skill or tool produces a downloadable file (DOCX, PPTX, etc.), the backend emits a `file_download` event as custom data:

```
2:[{"type":"file_download","file_id":"file_abc123","filename":"report.pptx","download_url":"/files/file_abc123/download","file_type":"pptx","size_kb":156.3,"tool_name":"skill:potomac-pptx-skill"}]
```

**Frontend should listen for `type === 'file_download'` in the `onData` callback and render a download button/card.**

### Example Complete Streaming Session (Skill with File)

```
0:"I'll create your presentation now.\n\n"
0:"Generating slides..."
0:" The presentation covers market outlook, sector analysis, and recommendations."
2:[{"type":"file_download","file_id":"file_xyz789","filename":"Q1_Market_Outlook.pptx","download_url":"/files/file_xyz789/download","file_type":"pptx","size_kb":203.4,"tool_name":"skill:potomac-pptx-skill"}]
d:{"finishReason":"stop","usage":{"promptTokens":1500,"completionTokens":6000},"skill":"potomac-pptx-skill","skillName":"Potomac PPTX Skill","executionTime":52.3}
```

### Example Complete Streaming Session (Chat with Tool)

```
0:"Let me create that document for you."
9:{"toolCallId":"call_123","toolName":"create_word_document","args":{"title":"Fund Fact Sheet","description":"..."}}
a:{"toolCallId":"call_123","result":"{\"success\":true,\"download_url\":\"/files/file_abc/download\",\"filename\":\"Fund_Fact_Sheet.docx\"}"}
2:[{"type":"file_download","file_id":"file_abc","filename":"Fund_Fact_Sheet.docx","download_url":"/files/file_abc/download","file_type":"docx","size_kb":45.2,"tool_name":"create_word_document"}]
e:{"finishReason":"tool-calls","usage":{"promptTokens":800,"completionTokens":200},"isContinued":true}
0:"Your Fund Fact Sheet has been generated and is ready to download."
d:{"finishReason":"stop","usage":{"promptTokens":1200,"completionTokens":500}}
```

---

## Rate Limits & Quotas

- **API Calls:** 120 req/min per IP
- **File Upload:** Max 50MB per file
- **Text Processing:** Max 5000 chars for TTS
- **Knowledge Base:** Unlimited documents

---

## SDK Integration Examples

### useChat() - React
```typescript
import { useChat } from '@ai-sdk/react';

export default function Chat() {
  const { messages, input, handleSubmit } = useChat({
    api: '/api/ai/chat',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  return <div>{/* UI */}</div>;
}
```

### useCompletion() - React
```typescript
import { useCompletion } from '@ai-sdk/react';

export default function CodeCompletion() {
  const { completion, input, handleSubmit } = useCompletion({
    api: '/api/ai/completion'
  });
  
  return <div>{/* UI */}</div>;
}
```

---

## Best Practices

1. **Always include Authorization header** except for public endpoints
2. **Handle rate limiting** with exponential backoff
3. **Stream long-running operations** (generation, research, analysis)
4. **Cache API keys** securely (never in frontend code)
5. **Validate file uploads** before sending to API
6. **Use conversation_id** to maintain context across requests
7. **Monitor WebSocket connections** for real-time updates
8. **Implement proper error boundaries** in frontend

---

## Support

For issues or questions:
- GitHub: https://github.com/sohaibali73/Potomac-Analyst-Workbench
- Documentation: https://potomac-analyst-workbench-production.up.railway.app/docs
- OpenAPI Spec: https://potomac-analyst-workbench-production.up.railway.app/openapi.json

