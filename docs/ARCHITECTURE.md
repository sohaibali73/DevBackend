# Analyst by Potomac — System Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER (Browser)                                │
└──────────────┬───────────────────────────────────┬───────────────────┘
               │                                   │
               ▼                                   ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│   Frontend (Next.js 16)  │        │  PresenterByPotomac      │
│   Vercel AI SDK v6       │        │  (Next.js 14, pptxgenjs) │
│   Deployed: Vercel       │        │  PPTX Microservice       │
│   URL: analystbypotomac  │        │  (Future integration)    │
│   .vercel.app            │        └──────────────────────────┘
└──────────────┬───────────┘
               │ SSE (UI Message Stream Protocol)
               │ /api/chat (protocol translator)
               ▼
┌──────────────────────────┐
│   Backend (FastAPI)      │
│   Python 3.11+           │
│   Deployed: Railway      │
│   URL: potomac-analyst-  │
│   workbench-production   │
│   .up.railway.app        │
└──────────┬───────┬───────┘
           │       │
           ▼       ▼
┌──────────┐ ┌──────────────┐
│ Claude   │ │  Supabase    │
│ API      │ │  (PostgreSQL │
│ (Anthro) │ │  + pgvector) │
└──────────┘ └──────────────┘
```

## Data Flow: Chat Message with Tool Call

### Streaming (Live)
```
1. User types "What's the weather in NYC?"
2. Frontend useChat.sendMessage() → POST /api/chat (Next.js route)
3. Next.js route → POST /chat/stream (Backend)
4. Backend → Claude API (with tools)
5. Claude decides to use get_weather tool
6. Backend streams: 7: tool-start → 9: tool-complete → a: tool-result → 0: text
7. Next.js route translates → SSE: tool-input-start → tool-output-available → text-delta
8. AI SDK useChat builds message.parts: [{type: 'tool-get_weather', state: 'output-available', output: {...}}, {type: 'text', text: '...'}]
9. Frontend renderMessage matches 'tool-get_weather' → <WeatherCard />
10. Backend saves to DB: metadata.parts includes tool invocation parts ← PERSISTENCE FIX
```

### Reload (From History)
```
1. User navigates back to conversation
2. Frontend loadPreviousMessages() → GET /chat/conversations/{id}/messages
3. Backend returns messages with metadata.parts containing tool invocation parts
4. Frontend sets messages via setMessages() with parts from metadata
5. renderMessage matches 'tool-get_weather' → <WeatherCard /> (same as streaming!)
```

## Frontend Architecture

### Key Components
- **ChatPage.tsx** — Main chat page, uses `useChat` hook with `DefaultChatTransport`
- **generative-ui/** — 30+ tool result components (WeatherCard, StockCard, etc.)
- **ai-elements/** — Composable UI primitives (Message, Tool, CodeBlock, etc.)
- **ArtifactRenderer** — Renders code/HTML/SVG artifacts

### State Management
- `useChat` (AI SDK) — Message state, streaming, transport
- `AuthContext` — JWT token, user info
- `ThemeContext` — Dark/light mode
- `TabProvider` — Tab/navigation state
- `conversationIdRef` — Synchronous conversation ID tracking

### API Routes (Next.js)
- `/api/chat` — Protocol translator (Backend Data Stream → UI Message Stream SSE)
- `/api/upload` — File upload proxy
- `/api/tts` — Text-to-speech proxy
- `/api/auth/*` — Auth proxies (to avoid CORS)

## Backend Architecture

### API Routes (FastAPI)
| Route Prefix | Purpose | Status |
|---|---|---|
| `/auth` | Authentication (JWT) | ✅ Working |
| `/chat` | Conversations, messages, streaming | ✅ Working |
| `/content` | Content feed | ❌ Broken (Coming Soon) |
| `/brain` | Knowledge base (RAG) | ⚠️ Partial |
| `/researcher` | Deep research | ⚠️ Partial |
| `/afl` | AFL code generation | ✅ Working |
| `/backtest` | Backtesting | ⚠️ Stub |
| `/presentations` | PPTX generation | ⚠️ Partial |
| `/train` | Training data | ✅ Working |
| `/reverse-engineer` | Strategy reverse engineering | ⚠️ Partial |
| `/admin` | Admin tools | ✅ Working |
| `/health` | Health check | ✅ Working |

### Core Modules
- **claude_engine.py** — Claude API integration
- **tools.py** — 40+ tool definitions and handlers
- **streaming.py** — Vercel AI SDK Data Stream Protocol encoder
- **artifact_parser.py** — Code/HTML/SVG artifact extraction from responses
- **context_manager.py** — Conversation context optimization

### Database (Supabase)
- **users** — User accounts, API keys
- **conversations** — Chat conversations
- **messages** — Chat messages (with JSONB metadata for parts/tools)
- **conversation_files** — Uploaded files per conversation
- **brain_documents** — Knowledge base documents
- **brain_chunks** — Document chunks with embeddings (pgvector)
- **training_data** — AFL training examples
- **user_feedback** — User feedback on responses
- **afl_codes** — Generated AFL code history
- **researcher_tasks** — Deep research task tracking
