# Analyst by Potomac API Documentation
**Version 3.6** | Base URL: `https://developer-potomaac.up.railway.app/`

---

## Overview
This is the official API documentation for the Analyst by Potomac AI-powered AmiBroker AFL development platform. This API provides streaming AI capabilities, financial data access, document processing, multi-agent systems, and trading strategy automation.

---

## Base Configuration
| Parameter | Value |
|-----------|-------|
| Base URL | `https://developer-potomaac.up.railway.app` |
| API Version | 3.6 |
| Rate Limit | **120 requests / minute** per IP address |
| CORS | Open to all origins (`*`) |
| Authentication | JWT Bearer Token (except public endpoints) |
| Response Format | JSON |
| Health Check | `GET /health` |
| OpenAPI Spec | `GET /openapi.json` |
| Interactive Docs | `GET /docs` (Swagger UI) |
| ReDoc UI | `GET /redoc` |

---

## Authentication
### Login Endpoint
```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Using Authentication Header
All protected endpoints require:
```http
Authorization: Bearer <your-access-token>
```

---

## Available API Endpoints

### 1. Authentication Module (`/auth/*`)
| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/auth/register` | POST | Create new user account | No |
| `/auth/login` | POST | Authenticate & get token | No |
| `/auth/refresh` | POST | Refresh access token | Yes |
| `/auth/me` | GET | Get current user profile | Yes |
| `/auth/logout` | POST | Invalidate current token | Yes |

### 2. AI & Chat Module (`/ai/*`, `/chat/*`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ai/chat` | POST | Streaming chat completion (Vercel AI SDK format) |
| `/ai/generate` | POST | Standard text generation |
| `/ai/stream` | GET | Server-Sent Events streaming |
| `/chat/message` | POST | Send chat message |
| `/chat/history` | GET | Get conversation history |

### 3. AFL Development Module (`/afl/*`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/afl/generate` | POST | Generate AmiBroker AFL code |
| `/afl/validate` | POST | Validate AFL syntax |
| `/afl/optimize` | POST | Optimize existing AFL indicators |
| `/afl/convert` | POST | Convert between AFL versions |
| `/afl/backtest` | POST | Run AFL backtesting |

### 4. Brain Knowledge Base (`/brain/*`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/brain/search` | POST | Semantic search in knowledge base |
| `/brain/add` | POST | Add documents to KB |
| `/brain/delete` | DELETE | Remove document from KB |
| `/brain/list` | GET | List all KB documents |

### 5. Financial Data Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/yfinance/quote` | GET | Get realtime stock quotes |
| `/yfinance/history` | GET | Historical price data |
| `/edgar/filings` | GET | SEC EDGAR filings lookup |
| `/edgar/xbrl` | GET | Financial statement data |

### 6. Agent Teams Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents/create` | POST | Create new agent team |
| `/agents/execute` | POST | Execute multi-agent task |
| `/agents/status` | GET | Check task status |
| `/agents/results` | GET | Get execution results |

### 7. File Processing Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload/file` | POST | Upload document file |
| `/upload/status` | GET | Check processing status |
| `/preview/docx` | POST | Extract DOCX content |
| `/preview/pptx` | POST | Extract PowerPoint content |

### 8. Training Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/train/start` | POST | Start model training |
| `/train/status` | GET | Training progress |
| `/train/models` | GET | List trained models |

### 9. Backtesting Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/backtest/run` | POST | Execute backtest |
| `/backtest/results` | GET | Get backtest report |
| `/backtest/optimize` | POST | Strategy optimization |

### 10. Skills & Tools Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/skills/list` | GET | List available skills |
| `/skills/execute` | POST | Execute specific skill |
| `/sandbox/python` | POST | Execute Python code |
| `/sandbox/javascript` | POST | Execute JavaScript code |

### 11. Background Tasks Module
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks/submit` | POST | Submit background task |
| `/tasks/status` | GET | Check task status |
| `/tasks/cancel` | POST | Cancel running task |

### 12. Presentation Generation
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/presentation/generate` | POST | Generate PPTX presentation |
| `/presentation/download` | GET | Download generated file |

### 13. Admin & Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/users` | GET | List all users |
| `/admin/stats` | GET | System statistics |
| `/health` | GET | System health check |

---

## Database Architecture

### Database System
- **Primary Database**: PostgreSQL 16
- **Vector Database**: pgvector extension (for embeddings)
- **Hosted on**: Supabase Cloud
- **Connection Pooling**: PgBouncer

### Core Database Schema

#### Tables:
1.  **`users`** - User accounts & profiles
2.  **`sessions`** - Authentication session tracking
3.  **`conversations`** - Chat conversation history
4.  **`messages`** - Individual chat messages
5.  **`knowledge_base`** - Vector embeddings for semantic search
6.  **`documents`** - Uploaded file metadata
7.  **`afl_scripts`** - Generated AFL code storage
8.  **`backtest_results`** - Backtesting report data
9.  **`agent_tasks`** - Multi-agent execution logs
10. **`background_tasks`** - Async task queue
11. **`api_usage`** - API request logging & analytics
12. **`training_jobs`** - Model training records

### Indexes & Optimization
- GIN indexes for vector similarity search
- B-Tree indexes on common query columns
- Partitioned tables for time-series data
- Materialized views for aggregated reports

---

## Error Handling
| Status Code | Meaning |
|-------------|---------|
| `200 OK` | Request successful |
| `201 Created` | Resource created successfully |
| `400 Bad Request` | Invalid input parameters |
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | Insufficient permissions |
| `404 Not Found` | Resource does not exist |
| `429 Too Many Requests` | Rate limit exceeded (Retry-After: 60) |
| `500 Internal Server Error` | Server side error |

**Error Response Format:**
```json
{
  "detail": "Human readable error message",
  "type": "ErrorTypeIdentifier"
}
```

---

## Rate Limiting
- **Limit**: 120 requests per minute per IP
- **Window**: 60 seconds
- **Exempt Endpoints**: `/`, `/health`, `/docs`, `/openapi.json`, `/redoc`
- **Retry-After** header provided when limit is reached

---

## Support
- Interactive API Docs: https://developer-potomaac.up.railway.app/docs
- Health Check: https://developer-potomaac.up.railway.app/health
- OpenAPI Spec: https://developer-potomaac.up.railway.app/openapi.json