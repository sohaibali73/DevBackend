# JavaScript Integration Guide
Analyst by Potomac API | Browser / Node.js / TypeScript

---

## Requirements
- Modern browser (Chrome 63+, Firefox 57+, Safari 11.1+) OR
- Node.js 18+
- Dependencies:
  - Built-in `fetch` API OR
  - `axios` (optional)
  - Native `EventSource` for streaming

---

## Step 1: Base API Client

```javascript
const BASE_URL = 'https://developer-potomaac.up.railway.app/';

class PotomacApiClient {
  constructor() {
    this.authToken = null;
  }
  
  setAuthToken(token) {
    this.authToken = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', token);
    }
  }
  
  clearAuthToken() {
    this.authToken = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
    }
  }
  
  getHeaders() {
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
    
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }
    
    return headers;
  }
  
  async request(method, path, body = null) {
    const options = {
      method,
      headers: this.getHeaders()
    };
    
    if (body) {
      options.body = JSON.stringify(body);
    }
    
    const response = await fetch(`${BASE_URL}${path}`, options);
    
    if (!response.ok) {
      if (response.status === 401) {
        this.clearAuthToken();
        throw new Error('Unauthorized');
      }
      
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After') || 60;
        const error = new Error('Rate limit exceeded');
        error.retryAfter = parseInt(retryAfter);
        throw error;
      }
      
      const errorData = await response.json();
      throw new Error(errorData.detail || `Request failed: ${response.status}`);
    }
    
    return response.json();
  }
}

export const apiClient = new PotomacApiClient();
```

---

## Step 2: Authentication

```javascript
export const authService = {
  async login(email, password) {
    const response = await fetch(`${BASE_URL}auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    if (!response.ok) {
      throw new Error('Login failed');
    }
    
    const data = await response.json();
    apiClient.setAuthToken(data.access_token);
    
    return data;
  },
  
  async register(email, password, name) {
    return apiClient.request('POST', 'auth/register', {
      email, password, name
    });
  },
  
  async logout() {
    await apiClient.request('POST', 'auth/logout');
    apiClient.clearAuthToken();
  },
  
  isAuthenticated() {
    return apiClient.authToken !== null;
  },
  
  restoreSession() {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token');
      if (token) {
        apiClient.setAuthToken(token);
        return true;
      }
    }
    return false;
  }
};
```

---

## Step 3: API Endpoints

### Chat Completion
```javascript
export const chatService = {
  async sendMessage(message) {
    return apiClient.request('POST', 'ai/chat', {
      message,
      stream: false
    });
  },
  
  streamChat(prompt, onChunk, onComplete) {
    const eventSource = new EventSource(`${BASE_URL}ai/stream?prompt=${encodeURIComponent(prompt)}`);
    
    eventSource.onmessage = (event) => {
      if (event.data === '[DONE]') {
        eventSource.close();
        onComplete?.();
        return;
      }
      
      onChunk?.(event.data);
    };
    
    eventSource.onerror = (error) => {
      eventSource.close();
      throw error;
    };
    
    return eventSource;
  }
};
```

### AFL Code Generation
```javascript
export const aflService = {
  async generate(description, type = 'indicator') {
    return apiClient.request('POST', 'afl/generate', {
      description,
      type
    });
  },
  
  async validate(code) {
    return apiClient.request('POST', 'afl/validate', { code });
  }
};
```

### File Upload
```javascript
export const fileService = {
  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${BASE_URL}upload/file`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiClient.authToken}`
      },
      body: formData
    });
    
    return response.json();
  }
};
```

### Financial Data
```javascript
export const financialService = {
  async getStockQuote(symbol) {
    return apiClient.request('GET', `yfinance/quote?symbol=${symbol}`);
  },
  
  async getHistoricalData(symbol, period = '1y') {
    return apiClient.request('GET', `yfinance/history?symbol=${symbol}&period=${period}`);
  },
  
  async getEdgarFilings(ticker, count = 10) {
    return apiClient.request('GET', `edgar/filings?ticker=${ticker}&count=${count}`);
  }
};
```

---

## Step 4: TypeScript Support

```typescript
interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

interface ChatResponse {
  content: string;
  model: string;
  created: number;
}

interface AflResponse {
  code: string;
  explanation: string;
  complexity: string;
}

interface ApiError {
  detail: string;
  type?: string;
}

// Type safe wrapper
async function apiRequest<T>(method: string, path: string, body?: any): Promise<T> {
  return apiClient.request(method, path, body) as Promise<T>;
}

// Usage:
const login = async (email: string, password: string): Promise<AuthResponse> => {
  return apiRequest<AuthResponse>('POST', 'auth/login', { email, password });
};
```

---

## Step 5: React Example

```jsx
import { useState, useEffect } from 'react';
import { chatService, authService } from './api';

function ChatComponent() {
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    authService.restoreSession();
  }, []);
  
  const handleSend = async () => {
    setLoading(true);
    try {
      const result = await chatService.sendMessage(message);
      setResponse(result.content);
    } catch (error) {
      console.error('Error:', error.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="p-6 max-w-xl mx-auto">
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Enter your message..."
        className="w-full p-3 border rounded"
      />
      
      <button
        onClick={handleSend}
        disabled={loading}
        className="mt-4 px-6 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
      >
        {loading ? 'Loading...' : 'Send'}
      </button>
      
      <div className="mt-6 p-4 bg-gray-50 rounded">
        {response}
      </div>
    </div>
  );
}

export default ChatComponent;
```

---

## Step 6: Node.js Usage

```javascript
// Node.js 18+ has built-in fetch
const { apiClient } = require('./api-client');

async function main() {
  // Login
  await apiClient.login('user@example.com', 'password');
  
  // Send chat message
  const response = await apiClient.request('POST', 'ai/chat', {
    message: 'Generate RSI indicator AFL code',
    stream: false
  });
  
  console.log('Response:', response.content);
}

main().catch(console.error);
```

---

## Step 7: Error Handling

```javascript
try {
  const result = await chatService.sendMessage(message);
} catch (error) {
  if (error.message === 'Unauthorized') {
    // Redirect to login
    window.location.href = '/login';
  } else if (error.message === 'Rate limit exceeded') {
    console.log(`Please retry after ${error.retryAfter} seconds`);
  } else {
    console.error('API Error:', error.message);
  }
}
```

---

## Best Practices
1.  Always handle 401 errors and redirect to login
2.  Implement exponential backoff for retries
3.  Use `AbortController` to cancel requests
4.  Store auth tokens in `HttpOnly` cookies for production websites
5.  Use interceptors (with axios) for automatic error handling
6.  Implement request queueing for rate limit handling
7.  Validate all API responses with schema validation (Zod / Yup)

---

## Supported Environments
✅ All modern web browsers
✅ Node.js 18+
✅ Deno
✅ Bun
✅ Electron
✅ React Native
✅ Next.js / Nuxt / SvelteKit

All API endpoints are fully compatible with JavaScript and TypeScript environments.