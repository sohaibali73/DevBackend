/**
 * Frontend API Client — Analyst by Potomac
 * ==========================================
 * Fully corrected JavaScript API client that matches the live backend routes.
 *
 * Backend base URL  : process.env.NEXT_PUBLIC_API_URL  (e.g. https://your-app.up.railway.app)
 * Auth              : Bearer JWT returned by /auth/login or /auth/register
 * Streaming         : Vercel AI SDK Data Stream Protocol  (type-code:JSON\n lines)
 * Canonical stream  : POST /chat/v6   (also aliased as /chat/stream for compat)
 *
 * Router prefixes in main.py
 * ─────────────────────────────────────────────────────────────────
 *  /auth           api/routes/auth.py
 *  /chat           api/routes/chat.py   (stream = /chat/v6)
 *  /afl            api/routes/afl.py
 *  /brain          api/routes/brain.py
 *  /backtest       api/routes/backtest.py
 *  /train          api/routes/train.py
 *  /researcher     api/routes/researcher.py
 *  /upload         api/routes/upload.py
 *  /skills         api/routes/skills.py
 *  /preview        api/routes/preview.py
 *  /health         api/routes/health.py
 *  /tasks          api/routes/tasks.py
 *  /generate_presentation  api/routes/generate_presentation.py
 *  /yfinance       api/routes/yfinance.py
 *  /edgar          api/routes/edgar.py
 * ─────────────────────────────────────────────────────────────────
 */

// ─── Helpers ─────────────────────────────────────────────────────────────────

const _storage = {
  getItem: (key) => {
    try { return typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null; }
    catch { return null; }
  },
  setItem: (key, val) => {
    try { if (typeof localStorage !== 'undefined') localStorage.setItem(key, val); }
    catch { /* SSR / strict env */ }
  },
  removeItem: (key) => {
    try { if (typeof localStorage !== 'undefined') localStorage.removeItem(key); }
    catch { /* SSR / strict env */ }
  },
};

// ─── API Client ───────────────────────────────────────────────────────────────

class APIClient {
  constructor() {
    this.baseUrl = (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL) || '';
    this._token = _storage.getItem('auth_token');
  }

  // ── token helpers ──────────────────────────────────────────────

  setToken(token) {
    this._token = token;
    _storage.setItem('auth_token', token);
  }

  getToken() {
    if (this._token) return this._token;
    const t = _storage.getItem('auth_token');
    this._token = t;
    return t;
  }

  clearToken() {
    this._token = null;
    _storage.removeItem('auth_token');
  }

  // ── core fetch ────────────────────────────────────────────────

  /**
   * @param {string}  endpoint    - path relative to baseUrl, e.g. '/auth/login'
   * @param {string}  method      - HTTP verb
   * @param {any}     body        - request body (JSON or FormData)
   * @param {boolean} isFormData  - when true body is sent as-is (no JSON serialisation)
   */
  async request(endpoint, method = 'GET', body = undefined, isFormData = false) {
    const headers = {};
    const token = this.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (!isFormData && method !== 'GET') headers['Content-Type'] = 'application/json';

    const config = { method, headers };
    if (body !== undefined) config.body = isFormData ? body : JSON.stringify(body);

    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        const err = await response.json().catch(() => ({
          detail: `Request failed with status ${response.status}`,
        }));
        throw new Error(err.detail || err.message || `HTTP ${response.status}`);
      }
      return response.json();
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error(
          `Cannot connect to API server at ${this.baseUrl}. ` +
          `Please check your internet connection or try again later.`,
        );
      }
      throw error;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // AUTH  /auth/*
  // ═══════════════════════════════════════════════════════════════

  /**
   * Register a new user.
   * Note: claude_api_key / tavily_api_key must be set separately via PUT /auth/me
   * after registration, or via PUT /auth/api-keys.
   *
   * Response: { access_token, token_type, user_id, email, expires_in }
   */
  async register(email, password, name) {
    const response = await this.request('/auth/register', 'POST', { email, password, name });
    if (response.access_token) this.setToken(response.access_token);
    return response;
  }

  /**
   * Login.
   * Response: { access_token, token_type, user_id, email, expires_in }
   */
  async login(email, password) {
    const response = await this.request('/auth/login', 'POST', { email, password });
    if (response.access_token) this.setToken(response.access_token);
    return response;
  }

  /** GET /auth/me — returns UserResponse */
  async getCurrentUser() {
    return this.request('/auth/me');
  }

  /**
   * PUT /auth/me — update name, nickname, or API keys.
   * All fields are optional.
   * @param {{ name?, nickname?, claude_api_key?, tavily_api_key? }} data
   */
  async updateProfile(data) {
    return this.request('/auth/me', 'PUT', data);
  }

  /**
   * PUT /auth/api-keys — dedicated endpoint for updating API keys only.
   * @param {{ claude_api_key?, tavily_api_key? }} data
   */
  async updateApiKeys(data) {
    return this.request('/auth/api-keys', 'PUT', data);
  }

  /** GET /auth/api-keys — returns { has_claude_key, has_tavily_key } */
  async getApiKeysStatus() {
    return this.request('/auth/api-keys');
  }

  /** POST /auth/logout */
  async logout() {
    try { await this.request('/auth/logout', 'POST'); } catch { /* ignore */ }
    this.clearToken();
  }

  /** POST /auth/forgot-password */
  async forgotPassword(email) {
    return this.request('/auth/forgot-password', 'POST', { email });
  }

  // ═══════════════════════════════════════════════════════════════
  // AFL  /afl/*
  // ═══════════════════════════════════════════════════════════════

  /**
   * POST /afl/generate
   * Response: { code, afl_code, explanation, stats }
   *
   * For conversation-based multi-step flow, pass conversation_id and/or answers.
   * Backtest settings shape:
   *   { initial_equity, position_size, position_size_type, max_positions,
   *     commission, trade_delays, margin_requirement }
   */
  async generateAFL({
    prompt,
    strategy_type = 'standalone',   // 'standalone' | 'composite'
    backtest_settings,
    settings,                        // legacy dict fallback
    conversation_id,
    answers,                         // { strategy_type: '...', trade_timing: '...' }
    stream = false,
    uploaded_file_ids,
    kb_context,
    thinking_mode,
    thinking_budget,
  }) {
    return this.request('/afl/generate', 'POST', {
      prompt,
      strategy_type,
      backtest_settings,
      settings,
      conversation_id,
      answers,
      stream,
      uploaded_file_ids,
      kb_context,
      thinking_mode,
      thinking_budget,
    });
  }

  /** POST /afl/optimize — response: { optimized_code } */
  async optimizeAFL(code) {
    return this.request('/afl/optimize', 'POST', { code });
  }

  /** POST /afl/debug — response: { debugged_code } */
  async debugAFL(code, errorMessage = '') {
    return this.request('/afl/debug', 'POST', { code, error_message: errorMessage });
  }

  /** POST /afl/explain — response: { explanation } */
  async explainAFL(code) {
    return this.request('/afl/explain', 'POST', { code });
  }

  /** POST /afl/validate — response: { valid, errors? } */
  async validateAFL(code) {
    return this.request('/afl/validate', 'POST', { code });
  }

  /** GET /afl/codes?limit=50 — list saved codes */
  async getAFLCodes(limit = 50) {
    return this.request(`/afl/codes?limit=${limit}`);
  }

  /** GET /afl/codes/:id */
  async getAFLCode(codeId) {
    return this.request(`/afl/codes/${codeId}`);
  }

  /** DELETE /afl/codes/:id */
  async deleteAFLCode(codeId) {
    return this.request(`/afl/codes/${codeId}`, 'DELETE');
  }

  // ── AFL File Uploads ─────────────────────────────────────────

  /**
   * POST /afl/upload  (multipart/form-data)
   * Supported types: CSV, TXT, PDF, AFL  (max 10 MB)
   * Response: { file_id, filename, content_type, size_bytes, preview }
   */
  async uploadAflFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request('/afl/upload', 'POST', formData, true);
  }

  /** GET /afl/files?limit=50 */
  async getAflFiles(limit = 50) {
    return this.request(`/afl/files?limit=${limit}`);
  }

  /** GET /afl/files/:id — includes full file_data */
  async getAflFile(fileId) {
    return this.request(`/afl/files/${fileId}`);
  }

  /** DELETE /afl/files/:id */
  async deleteAflFile(fileId) {
    return this.request(`/afl/files/${fileId}`, 'DELETE');
  }

  // ── AFL Settings Presets ─────────────────────────────────────

  /**
   * POST /afl/settings/presets
   * Body: { name, settings: BacktestSettingsInput, is_default? }
   * BacktestSettingsInput: { initial_equity, position_size, position_size_type,
   *                          max_positions, commission, trade_delays, margin_requirement }
   */
  async saveSettingsPreset(preset) {
    return this.request('/afl/settings/presets', 'POST', preset);
  }

  /** GET /afl/settings/presets */
  async getSettingsPresets() {
    return this.request('/afl/settings/presets');
  }

  /** GET /afl/settings/presets/:id */
  async getSettingsPreset(presetId) {
    return this.request(`/afl/settings/presets/${presetId}`);
  }

  /** PUT /afl/settings/presets/:id */
  async updateSettingsPreset(presetId, updates) {
    return this.request(`/afl/settings/presets/${presetId}`, 'PUT', updates);
  }

  /** DELETE /afl/settings/presets/:id */
  async deleteSettingsPreset(presetId) {
    return this.request(`/afl/settings/presets/${presetId}`, 'DELETE');
  }

  /** POST /afl/settings/presets/:id/set-default */
  async setDefaultPreset(presetId) {
    return this.request(`/afl/settings/presets/${presetId}/set-default`, 'POST');
  }

  // ── AFL History ───────────────────────────────────────────────

  /**
   * POST /afl/history
   * IMPORTANT: backend field names differ from earlier versions:
   *   strategy_description  (not "prompt")
   *   generated_code
   *   strategy_type
   *   timestamp             (optional ISO string)
   */
  async saveAflHistory({ strategy_description, generated_code, strategy_type, timestamp }) {
    return this.request('/afl/history', 'POST', {
      strategy_description,
      generated_code,
      strategy_type,
      timestamp,
    });
  }

  /** GET /afl/history?limit=50 */
  async getAflHistory(limit = 50) {
    return this.request(`/afl/history?limit=${limit}`);
  }

  /** DELETE /afl/history/:id */
  async deleteAflHistory(historyId) {
    return this.request(`/afl/history/${historyId}`, 'DELETE');
  }

  // ═══════════════════════════════════════════════════════════════
  // CHAT  /chat/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /chat/conversations */
  async getConversations() {
    return this.request('/chat/conversations');
  }

  /**
   * POST /chat/conversations
   * @param {string} title
   * @param {string} conversationType  - 'agent' | 'afl_generation'
   */
  async createConversation(title = 'New Conversation', conversationType = 'agent') {
    return this.request('/chat/conversations', 'POST', {
      title,
      conversation_type: conversationType,
    });
  }

  /** GET /chat/conversations/:id/messages */
  async getMessages(conversationId) {
    return this.request(`/chat/conversations/${conversationId}/messages`);
  }

  /** PATCH /chat/conversations/:id — rename */
  async renameConversation(conversationId, title) {
    return this.request(`/chat/conversations/${conversationId}`, 'PATCH', { title });
  }

  /** DELETE /chat/conversations/:id */
  async deleteConversation(conversationId) {
    return this.request(`/chat/conversations/${conversationId}`, 'DELETE');
  }

  /**
   * POST /chat/message  (non-streaming)
   * Response: { conversation_id, response, parts, tools_used, downloadable_files, all_artifacts }
   */
  async sendMessage(content, conversationId) {
    return this.request('/chat/message', 'POST', {
      content,
      conversation_id: conversationId,
    });
  }

  /** GET /chat/tools — lists available tools */
  async getChatTools() {
    return this.request('/chat/tools');
  }

  // ── Streaming (Vercel AI SDK Data Stream Protocol) ────────────

  /**
   * POST /chat/v6  — canonical production streaming endpoint.
   *
   * Stream protocol: each line is   TYPE_CODE:JSON_VALUE\n
   *   '0'  text delta          (string)
   *   '2'  data part           (array — artifacts / metadata)
   *   '3'  error               (string | { message })
   *   '9'  tool call           ({ toolCallId, toolName, args })
   *   'a'  tool result         ({ toolCallId, result })
   *   'd'  finish message      ({ finishReason, usage })
   *   'e'  finish step         (unused)
   *
   * Conversation ID is returned in the response header X-Conversation-Id.
   *
   * @returns {Promise<{ conversationId: string }>}
   */
  async sendMessageStream(content, conversationId, options = {}) {
    return this._streamRequest('/chat/v6', content, conversationId, options);
  }

  /**
   * Alias of sendMessageStream — both hit /chat/v6.
   * Kept for backward compatibility with code using sendMessageStreamV6.
   */
  async sendMessageStreamV6(content, conversationId, options = {}) {
    return this._streamRequest('/chat/v6', content, conversationId, options);
  }

  /** Returns the streaming endpoint URL. */
  getStreamEndpoint() {
    return `${this.baseUrl}/chat/v6`;
  }

  // ── internal stream helper ────────────────────────────────────

  async _streamRequest(endpoint, content, conversationId, options = {}) {
    const token = this.getToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers,
      signal: options.signal,
      body: JSON.stringify({ content, conversation_id: conversationId }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({
        detail: `Request failed with status ${response.status}`,
      }));
      throw new Error(err.detail || err.message || `HTTP ${response.status}`);
    }

    const newConversationId =
      response.headers.get('X-Conversation-Id') || conversationId || '';

    if (!response.body) throw new Error('Response body is null');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const processLine = (line) => {
      if (!line.trim()) return;
      const typeCode = line[0];
      const raw = line.substring(2); // skip "X:" prefix
      if (!raw) return;

      try {
        const parsed = JSON.parse(raw);
        switch (typeCode) {
          case '0': // text delta
            options.onText?.(typeof parsed === 'string' ? parsed : parsed.text || '');
            break;
          case '2': // data (artifacts, metadata)
            options.onData?.(parsed);
            break;
          case '3': // error
            options.onError?.(typeof parsed === 'string' ? parsed : (parsed.message || 'Unknown error'));
            break;
          case '9': // tool call
            if (parsed.toolCallId && parsed.toolName)
              options.onToolCall?.(parsed.toolCallId, parsed.toolName, parsed.args || {});
            break;
          case 'a': // tool result
            if (parsed.toolCallId)
              options.onToolResult?.(parsed.toolCallId, parsed.result);
            break;
          case 'd': // finish
            if (parsed.finishReason)
              options.onFinish?.(parsed.finishReason, parsed.usage || {});
            break;
          case 'e': // finish step (no-op)
            break;
          default:
            console.warn('[stream] unknown type code:', typeCode, raw.substring(0, 80));
        }
      } catch (e) {
        console.warn('[stream] parse error on line:', line.substring(0, 100), e);
      }
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(processLine);
      }
      if (buffer.trim()) processLine(buffer);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      options.onError?.(msg);
      throw error;
    }

    return { conversationId: newConversationId };
  }

  // ── File upload to conversation ───────────────────────────────

  /**
   * POST /upload/conversations/:conversationId
   * Accepts a FormData with 'file' field.
   */
  async uploadConversationFile(conversationId, formData) {
    const token = this.getToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(
      `${this.baseUrl}/upload/conversations/${conversationId}`,
      { method: 'POST', headers, body: formData },
    );
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  // ═══════════════════════════════════════════════════════════════
  // BRAIN / KNOWLEDGE BASE  /brain/*
  // ═══════════════════════════════════════════════════════════════

  /**
   * POST /brain/upload  (multipart)
   * Response: { status, document_id, storage_path, classification, chunks_created }
   *           or { status: 'duplicate', document_id }
   */
  async uploadDocument(file, title, category = 'general') {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    formData.append('category', category);
    return this.request('/brain/upload', 'POST', formData, true);
  }

  /**
   * POST /brain/upload-batch  (multipart, multiple files)
   * Response: { status, summary: { total, successful, duplicates, failed }, results }
   */
  async uploadDocumentsBatch(files, category = 'general') {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    formData.append('category', category);
    return this.request('/brain/upload-batch', 'POST', formData, true);
  }

  /**
   * POST /brain/upload-text
   * Response: { status, document_id }
   */
  async uploadText(text, title, category = 'general') {
    return this.request('/brain/upload-text', 'POST', { title, content: text, category });
  }

  /**
   * POST /brain/search
   * Response: { results, count, search_type: 'vector' | 'text' }
   */
  async searchKnowledge(query, category, limit = 10) {
    return this.request('/brain/search', 'POST', { query, category, limit });
  }

  /**
   * GET /brain/documents?category=&limit=50
   */
  async getDocuments(category, limit = 50) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (category) params.append('category', category);
    return this.request(`/brain/documents?${params}`);
  }

  /**
   * GET /brain/documents/:id — includes raw_content
   */
  async getDocument(documentId) {
    return this.request(`/brain/documents/${documentId}`);
  }

  /**
   * GET /brain/documents/:id/download — returns binary blob via direct fetch
   */
  async downloadDocument(documentId) {
    const token = this.getToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`${this.baseUrl}/brain/documents/${documentId}/download`, {
      headers,
    });
    if (!response.ok) throw new Error(`Download failed: ${response.status}`);
    return response.blob();
  }

  /**
   * GET /brain/stats
   * Response: { total_documents, total_size, total_size_on_disk_mb,
   *             total_chunks, total_learnings, categories }
   */
  async getBrainStats() {
    return this.request('/brain/stats');
  }

  /** DELETE /brain/documents/:id */
  async deleteDocument(documentId) {
    return this.request(`/brain/documents/${documentId}`, 'DELETE');
  }

  // ═══════════════════════════════════════════════════════════════
  // BACKTEST  /backtest/*
  // ═══════════════════════════════════════════════════════════════

  /** POST /backtest/upload */
  async uploadBacktest(file, strategyId) {
    const formData = new FormData();
    formData.append('file', file);
    if (strategyId) formData.append('strategy_id', strategyId);
    return this.request('/backtest/upload', 'POST', formData, true);
  }

  /** GET /backtest/:id */
  async getBacktest(backtestId) {
    return this.request(`/backtest/${backtestId}`);
  }

  /** GET /backtest/strategy/:strategyId */
  async getStrategyBacktests(strategyId) {
    return this.request(`/backtest/strategy/${strategyId}`);
  }

  // ═══════════════════════════════════════════════════════════════
  // RESEARCHER  /researcher/*
  //
  // NOTE: all responses are wrapped:
  //   { success: true, data: {...}, message: "..." }
  //   Unwrap via response.data
  // ═══════════════════════════════════════════════════════════════

  /** GET /researcher/company/:symbol */
  async getCompanyResearch(symbol) {
    return this.request(`/researcher/company/${symbol}`);
  }

  /**
   * GET /researcher/news/:symbol?limit=20
   * Response.data: { symbol, news, sentiment_score, news_count }
   */
  async getCompanyNews(symbol, limit = 20) {
    return this.request(`/researcher/news/${symbol}?limit=${limit}`);
  }

  /**
   * POST /researcher/strategy-analysis
   * Body: { symbol, strategy_type, timeframe, additional_context? }
   */
  async analyzeStrategyFit(symbol, strategy_type, timeframe, additional_context) {
    return this.request('/researcher/strategy-analysis', 'POST', {
      symbol,
      strategy_type,
      timeframe,
      additional_context,
    });
  }

  /**
   * POST /researcher/comparison
   * Body: { symbol, peers: string[] }
   */
  async getPeerComparison(symbol, peers = [], sector) {
    return this.request('/researcher/comparison', 'POST', { symbol, peers, sector });
  }

  /** GET /researcher/macro-context */
  async getMacroContext() {
    return this.request('/researcher/macro-context');
  }

  /** GET /researcher/sec-filings/:symbol */
  async getSecFilings(symbol) {
    return this.request(`/researcher/sec-filings/${symbol}`);
  }

  /**
   * POST /researcher/generate-report
   * Body: { symbol, report_type?, sections?, format? }
   */
  async generateResearchReport(symbol, {
    report_type = 'company',
    sections = ['executive_summary', 'fundamental_analysis'],
    format = 'json',
  } = {}) {
    return this.request('/researcher/generate-report', 'POST', {
      symbol,
      report_type,
      sections,
      format,
    });
  }

  /** GET /researcher/trending?limit=10 */
  async getTrendingResearch(limit = 10) {
    return this.request(`/researcher/trending?limit=${limit}`);
  }

  /** GET /researcher/search?query=&search_type=company&limit=10 */
  async searchResearch(query, searchType = 'company', limit = 10) {
    const params = new URLSearchParams({ query, search_type: searchType, limit: String(limit) });
    return this.request(`/researcher/search?${params}`);
  }

  // ═══════════════════════════════════════════════════════════════
  // TRAIN  /train/*
  //
  // NOTE: some list endpoints return { count, feedback } or { count, suggestions }
  //       rather than a plain array.
  // ═══════════════════════════════════════════════════════════════

  /**
   * POST /train/feedback
   * Body: { code_id?, conversation_id?, original_prompt, generated_code,
   *         feedback_type, feedback_text, correct_code?, rating? }
   * feedback_type: 'correction' | 'improvement' | 'bug' | 'praise'
   * Response: { status, feedback_id, message }
   */
  async submitFeedback(feedback) {
    return this.request('/train/feedback', 'POST', feedback);
  }

  /**
   * GET /train/feedback/my?limit=50
   * Response: { count, feedback: [...] }
   */
  async getMyFeedback(limit = 50) {
    return this.request(`/train/feedback/my?limit=${limit}`);
  }

  /** GET /train/feedback/:id */
  async getFeedback(feedbackId) {
    return this.request(`/train/feedback/${feedbackId}`);
  }

  /**
   * POST /train/test
   * Body: { prompt, category?, include_training? }
   * Response: { prompt, without_training, with_training, training_context_used, differences_detected }
   */
  async testTraining(data) {
    return this.request('/train/test', 'POST', data);
  }

  /**
   * GET /train/effectiveness
   * Response: { average_rating, total_feedback, correction_rate, corrections_count,
   *             training_examples, active_training, training_by_type }
   */
  async getTrainingEffectiveness() {
    return this.request('/train/effectiveness');
  }

  /**
   * POST /train/suggest
   * Body: { title, description, example_input?, example_output?, reason }
   * Response: { status, suggestion_id, message }
   */
  async suggestTraining(suggestion) {
    return this.request('/train/suggest', 'POST', suggestion);
  }

  /**
   * GET /train/suggestions/my?limit=50
   * Response: { count, suggestions: [...] }
   */
  async getMySuggestions(limit = 50) {
    return this.request(`/train/suggestions/my?limit=${limit}`);
  }

  /**
   * GET /train/analytics/learning-curve
   * Response: { total_codes_generated, average_quality_score, average_user_rating,
   *             recent_codes, recent_feedback, trend }
   */
  async getLearningCurve() {
    return this.request('/train/analytics/learning-curve');
  }

  /**
   * GET /train/analytics/popular-patterns?limit=10
   * Response: { popular_patterns, count }
   */
  async getPopularPatterns(limit = 10) {
    return this.request(`/train/analytics/popular-patterns?limit=${limit}`);
  }

  /**
   * GET /train/knowledge/search?query=&category=&limit=10
   * Response: { query, matches, total_matches }
   */
  async searchTrainingKnowledge(query, category, limit = 10) {
    const params = new URLSearchParams({ query, limit: String(limit) });
    if (category) params.append('category', category);
    return this.request(`/train/knowledge/search?${params}`);
  }

  /**
   * GET /train/knowledge/categories
   * Response: { categories: { [category]: count }, total }
   */
  async getKnowledgeCategories() {
    return this.request('/train/knowledge/categories');
  }

  /**
   * GET /train/knowledge/types
   * Response: { training_types: [{ type, count, description }], total }
   */
  async getTrainingTypes() {
    return this.request('/train/knowledge/types');
  }

  /**
   * POST /train/quick-learn
   * Body: { code, explanation }  — Note: backend reads from query params in some versions;
   *        body form is preferred.
   * Response: { status, suggestion_id, message }
   */
  async quickLearn(code, explanation) {
    return this.request('/train/quick-learn', 'POST', { code, explanation });
  }

  /**
   * GET /train/stats
   * Response: training_manager.get_training_stats() shape
   */
  async getTrainStats() {
    return this.request('/train/stats');
  }

  // ═══════════════════════════════════════════════════════════════
  // PRESENTATIONS  /generate_presentation/*
  // ═══════════════════════════════════════════════════════════════

  /**
   * Generate a PPTX presentation (returns a raw fetch Response for streaming).
   * Caller is responsible for consuming the blob.
   *
   * Body: { title, slides, theme, format: 'pptx' }
   * slide element types: 'text' | 'image' | 'chart' | 'table' | 'shape'
   */
  async generatePresentation(payload) {
    const token = this.getToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${this.baseUrl}/generate_presentation/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    return response; // caller calls .blob() to download the PPTX
  }

  // ═══════════════════════════════════════════════════════════════
  // SKILLS  /skills/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /skills */
  async getSkills() {
    return this.request('/skills');
  }

  /** GET /skills/jobs */
  async getSkillJobs() {
    return this.request('/skills/jobs');
  }

  // ═══════════════════════════════════════════════════════════════
  // YFINANCE  /yfinance/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /yfinance/quote/:symbol */
  async getYFinanceQuote(symbol) {
    return this.request(`/yfinance/quote/${symbol}`);
  }

  /** GET /yfinance/history/:symbol?period=1y&interval=1d */
  async getYFinanceHistory(symbol, period = '1y', interval = '1d') {
    return this.request(`/yfinance/history/${symbol}?period=${period}&interval=${interval}`);
  }

  // ═══════════════════════════════════════════════════════════════
  // EDGAR  /edgar/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /edgar/filings/:symbol */
  async getEdgarFilings(symbol) {
    return this.request(`/edgar/filings/${symbol}`);
  }

  // ═══════════════════════════════════════════════════════════════
  // TASKS  /tasks/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /tasks */
  async getTasks() {
    return this.request('/tasks');
  }

  /** GET /tasks/:id */
  async getTask(taskId) {
    return this.request(`/tasks/${taskId}`);
  }

  // ═══════════════════════════════════════════════════════════════
  // HEALTH  /health/*
  // ═══════════════════════════════════════════════════════════════

  /** GET /health */
  async checkHealth() {
    return this.request('/health');
  }
}

// ─── Singleton export ─────────────────────────────────────────────────────────

export const apiClient = new APIClient();
export default apiClient;

// ─── Convenience namespace API ────────────────────────────────────────────────
// One-liner wrappers so callers can do:  api.auth.login(email, pass)

export const api = {

  auth: {
    register:        (email, password, name) => apiClient.register(email, password, name),
    login:           (email, password)       => apiClient.login(email, password),
    getMe:           ()                      => apiClient.getCurrentUser(),
    updateProfile:   (data)                  => apiClient.updateProfile(data),
    updateApiKeys:   (data)                  => apiClient.updateApiKeys(data),
    getApiKeysStatus:()                      => apiClient.getApiKeysStatus(),
    logout:          ()                      => apiClient.logout(),
    forgotPassword:  (email)                 => apiClient.forgotPassword(email),
  },

  afl: {
    generate:         (opts)                             => apiClient.generateAFL(opts),
    optimize:         (code)                             => apiClient.optimizeAFL(code),
    debug:            (code, errorMessage)               => apiClient.debugAFL(code, errorMessage),
    explain:          (code)                             => apiClient.explainAFL(code),
    validate:         (code)                             => apiClient.validateAFL(code),
    getCodes:         (limit)                            => apiClient.getAFLCodes(limit),
    getCode:          (codeId)                           => apiClient.getAFLCode(codeId),
    deleteCode:       (codeId)                           => apiClient.deleteAFLCode(codeId),
    // File uploads
    uploadFile:       (file)                             => apiClient.uploadAflFile(file),
    getFiles:         (limit)                            => apiClient.getAflFiles(limit),
    getFile:          (fileId)                           => apiClient.getAflFile(fileId),
    deleteFile:       (fileId)                           => apiClient.deleteAflFile(fileId),
    // Settings presets
    savePreset:       (preset)                           => apiClient.saveSettingsPreset(preset),
    getPresets:       ()                                 => apiClient.getSettingsPresets(),
    getPreset:        (presetId)                         => apiClient.getSettingsPreset(presetId),
    updatePreset:     (presetId, updates)                => apiClient.updateSettingsPreset(presetId, updates),
    deletePreset:     (presetId)                         => apiClient.deleteSettingsPreset(presetId),
    setDefaultPreset: (presetId)                         => apiClient.setDefaultPreset(presetId),
    // History — NOTE: field is strategy_description, not prompt
    saveHistory:      (entry)                            => apiClient.saveAflHistory(entry),
    getHistory:       (limit)                            => apiClient.getAflHistory(limit),
    deleteHistory:    (historyId)                        => apiClient.deleteAflHistory(historyId),
  },

  chat: {
    getConversations:    ()                                    => apiClient.getConversations(),
    createConversation:  (title, type)                         => apiClient.createConversation(title, type),
    getMessages:         (conversationId)                      => apiClient.getMessages(conversationId),
    renameConversation:  (conversationId, title)               => apiClient.renameConversation(conversationId, title),
    deleteConversation:  (conversationId)                      => apiClient.deleteConversation(conversationId),
    sendMessage:         (content, conversationId)             => apiClient.sendMessage(content, conversationId),
    sendMessageStream:   (content, conversationId, options)    => apiClient.sendMessageStream(content, conversationId, options),
    sendMessageStreamV6: (content, conversationId, options)    => apiClient.sendMessageStreamV6(content, conversationId, options),
    uploadFile:          (conversationId, formData)            => apiClient.uploadConversationFile(conversationId, formData),
    getStreamEndpoint:   ()                                    => apiClient.getStreamEndpoint(),
    getTools:            ()                                    => apiClient.getChatTools(),
  },

  brain: {
    uploadDocument:      (file, title, category) => apiClient.uploadDocument(file, title, category),
    uploadBatch:         (files, category)       => apiClient.uploadDocumentsBatch(files, category),
    uploadText:          (text, title, category) => apiClient.uploadText(text, title, category),
    search:              (query, category, limit)=> apiClient.searchKnowledge(query, category, limit),
    getDocuments:        (category, limit)       => apiClient.getDocuments(category, limit),
    getDocument:         (documentId)            => apiClient.getDocument(documentId),
    downloadDocument:    (documentId)            => apiClient.downloadDocument(documentId),
    getStats:            ()                      => apiClient.getBrainStats(),
    deleteDocument:      (documentId)            => apiClient.deleteDocument(documentId),
  },

  backtest: {
    upload:              (file, strategyId) => apiClient.uploadBacktest(file, strategyId),
    getBacktest:         (backtestId)       => apiClient.getBacktest(backtestId),
    getStrategyBacktests:(strategyId)       => apiClient.getStrategyBacktests(strategyId),
  },

  researcher: {
    getCompanyResearch:  (symbol)                                            => apiClient.getCompanyResearch(symbol),
    getCompanyNews:      (symbol, limit)                                     => apiClient.getCompanyNews(symbol, limit),
    analyzeStrategyFit:  (symbol, strategy_type, timeframe, ctx)             => apiClient.analyzeStrategyFit(symbol, strategy_type, timeframe, ctx),
    getPeerComparison:   (symbol, peers, sector)                             => apiClient.getPeerComparison(symbol, peers, sector),
    getMacroContext:     ()                                                  => apiClient.getMacroContext(),
    getSecFilings:       (symbol)                                            => apiClient.getSecFilings(symbol),
    generateReport:      (symbol, opts)                                      => apiClient.generateResearchReport(symbol, opts),
    getTrending:         (limit)                                             => apiClient.getTrendingResearch(limit),
    search:              (query, type, limit)                                => apiClient.searchResearch(query, type, limit),
  },

  train: {
    submitFeedback:       (feedback)          => apiClient.submitFeedback(feedback),
    // returns { count, feedback: [...] }
    getMyFeedback:        (limit)             => apiClient.getMyFeedback(limit),
    getFeedback:          (feedbackId)        => apiClient.getFeedback(feedbackId),
    testTraining:         (data)              => apiClient.testTraining(data),
    getEffectiveness:     ()                  => apiClient.getTrainingEffectiveness(),
    suggest:              (suggestion)        => apiClient.suggestTraining(suggestion),
    // returns { count, suggestions: [...] }
    getMySuggestions:     (limit)             => apiClient.getMySuggestions(limit),
    getLearningCurve:     ()                  => apiClient.getLearningCurve(),
    getPopularPatterns:   (limit)             => apiClient.getPopularPatterns(limit),
    searchKnowledge:      (query, cat, limit) => apiClient.searchTrainingKnowledge(query, cat, limit),
    getCategories:        ()                  => apiClient.getKnowledgeCategories(),
    getTypes:             ()                  => apiClient.getTrainingTypes(),
    quickLearn:           (code, explanation) => apiClient.quickLearn(code, explanation),
    getStats:             ()                  => apiClient.getTrainStats(),
  },

  presentations: {
    generate: (payload) => apiClient.generatePresentation(payload),
  },

  skills: {
    getSkills:    () => apiClient.getSkills(),
    getSkillJobs: () => apiClient.getSkillJobs(),
  },

  yfinance: {
    getQuote:   (symbol)                    => apiClient.getYFinanceQuote(symbol),
    getHistory: (symbol, period, interval)  => apiClient.getYFinanceHistory(symbol, period, interval),
  },

  edgar: {
    getFilings: (symbol) => apiClient.getEdgarFilings(symbol),
  },

  tasks: {
    getTasks: ()         => apiClient.getTasks(),
    getTask:  (taskId)   => apiClient.getTask(taskId),
  },

  health: {
    check: () => apiClient.checkHealth(),
  },
};


// ─── Usage examples ───────────────────────────────────────────────────────────

/**
 * ── Login ────────────────────────────────────────────────────────────────────
 *
 *   const { access_token, user_id } = await api.auth.login('user@example.com', 'pass');
 *
 * ── Register ─────────────────────────────────────────────────────────────────
 *
 *   const { access_token } = await api.auth.register('user@example.com', 'pass', 'Name');
 *   // Then set API keys:
 *   await api.auth.updateApiKeys({ claude_api_key: 'sk-...', tavily_api_key: 'tvly-...' });
 *
 * ── Non-streaming chat ───────────────────────────────────────────────────────
 *
 *   const { response, conversation_id } = await api.chat.sendMessage('Hello!');
 *
 * ── Streaming chat ───────────────────────────────────────────────────────────
 *
 *   const { conversationId } = await api.chat.sendMessageStream(
 *     'Write an AFL strategy',
 *     undefined,            // start new conversation
 *     {
 *       onText: (text) => process.stdout.write(text),
 *       onData: (data) => console.log('artifact/metadata:', data),
 *       onToolCall: (id, name, args) => console.log('tool:', name, args),
 *       onToolResult: (id, result) => console.log('tool result:', result),
 *       onFinish: (reason, usage) => console.log('done', reason, usage),
 *       onError: (err) => console.error('stream error:', err),
 *     },
 *   );
 *
 * ── AFL generation ───────────────────────────────────────────────────────────
 *
 *   const { code, explanation } = await api.afl.generate({
 *     prompt: 'RSI crossover strategy',
 *     strategy_type: 'standalone',
 *     backtest_settings: {
 *       initial_equity: 100000,
 *       position_size: '100',
 *       commission: 0.0005,
 *       trade_delays: [0,0,0,0],
 *     },
 *   });
 *
 * ── Save AFL history ─────────────────────────────────────────────────────────
 *
 *   // NOTE: use strategy_description (not prompt)
 *   await api.afl.saveHistory({
 *     strategy_description: 'RSI crossover',
 *     generated_code: code,
 *     strategy_type: 'standalone',
 *   });
 *
 * ── Brain search ─────────────────────────────────────────────────────────────
 *
 *   const { results, count, search_type } = await api.brain.search('RSI strategy', 'afl', 5);
 *
 * ── Researcher (responses wrapped in { success, data, message }) ──────────────
 *
 *   const res = await api.researcher.getCompanyResearch('AAPL');
 *   const data = res.data;   // unwrap
 *
 * ── Training feedback ────────────────────────────────────────────────────────
 *
 *   await api.train.submitFeedback({
 *     original_prompt: 'RSI crossover',
 *     generated_code: code,
 *     feedback_type: 'correction',
 *     feedback_text: 'RSI() should not take Close as first arg',
 *     correct_code: fixedCode,
 *     rating: 3,
 *   });
 *
 * ── Get my feedback (unwrap array) ───────────────────────────────────────────
 *
 *   const { feedback, count } = await api.train.getMyFeedback();
 *
 * ── Presentation export ──────────────────────────────────────────────────────
 *
 *   const response = await api.presentations.generate({
 *     title: 'Q1 Report',
 *     slides: [...],
 *     theme: 'potomac',
 *     format: 'pptx',
 *   });
 *   const blob = await response.blob();
 *   const url = URL.createObjectURL(blob);
 *   const a = document.createElement('a');
 *   a.href = url; a.download = 'Q1_Report.pptx'; a.click();
 */
