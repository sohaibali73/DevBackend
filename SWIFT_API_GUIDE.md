# Analyst by Potomac — Complete Swift / SwiftUI API Guide

> **Base URL:** `https://developer-potomaac.up.railway.app/`
>
> **API Version:** 2.0
>
> **Protocol:** All endpoints require HTTPS. Most endpoints require a Bearer JWT token from Supabase Auth.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Authentication (`/auth`)](#2-authentication)
3. [Chat & Conversations (`/chat`)](#3-chat--conversations)
4. [AI SDK Streaming (`/ai`)](#4-ai-sdk-streaming)
5. [AFL Code Generation (`/afl`)](#5-afl-code-generation)
6. [Knowledge Base / Brain (`/brain`)](#6-knowledge-base--brain)
7. [File Upload (`/upload`)](#7-file-upload)
8. [Generated Files (`/files`)](#8-generated-files)
9. [Backtest Analysis (`/backtest`)](#9-backtest-analysis)
10. [Researcher (`/researcher`)](#10-researcher)
11. [Skills (`/skills`)](#11-skills)
12. [YFinance Data (`/yfinance`)](#12-yfinance-data)
13. [SEC EDGAR (`/edgar`)](#13-sec-edgar)
14. [Background Tasks (`/tasks`)](#14-background-tasks)
15. [Consensus (`/consensus`)](#15-consensus)
16. [Training (`/train`)](#16-training)
17. [Admin (`/admin`)](#17-admin)
18. [Presentation Generation (`/api/generate-presentation`)](#18-presentation-generation)
19. [KB Admin Bulk Upload (`/kb-admin`)](#19-kb-admin-bulk-upload)
20. [Health & Diagnostics (`/health`)](#20-health--diagnostics)
21. [Rate Limiting](#21-rate-limiting)
22. [Error Handling](#22-error-handling)
23. [Complete Swift Networking Layer](#23-complete-swift-networking-layer)

---

## 1. Getting Started

### Base Configuration

```swift
import Foundation

// MARK: - API Configuration
struct APIConfig {
    static let baseURL = "https://developer-potomaac.up.railway.app"
    static let contentType = "application/json"
    
    // Supabase Auth credentials (get these from your Supabase project)
    static let supabaseURL = "YOUR_SUPABASE_URL"
    static let supabaseAnonKey = "YOUR_SUPABASE_ANON_KEY"
}
```

### Authentication Model

Most endpoints require a **Bearer JWT token** obtained from Supabase Auth via the `/auth/login` or `/auth/register` endpoints. Pass it in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### Swift Data Models

```swift
import Foundation

// MARK: - Core Models
struct Token: Codable {
    let accessToken: String
    let tokenType: String
    let userId: String
    let email: String
    let expiresIn: Int
    
    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case userId = "user_id"
        case email
        case expiresIn = "expires_in"
    }
}

struct APIError: Codable, Error {
    let detail: String
}

struct UserResponse: Codable {
    let id: String
    let email: String
    let name: String?
    let nickname: String?
    let isAdmin: Bool
    let isActive: Bool
    let hasApiKeys: Bool
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id, email, name, nickname
        case isAdmin = "is_admin"
        case isActive = "is_active"
        case hasApiKeys = "has_api_keys"
        case createdAt = "created_at"
    }
}
```

### Reusable Network Service

```swift
import Foundation
import Combine

// MARK: - Network Service
class NetworkService: ObservableObject {
    static let shared = NetworkService()
    
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    
    @Published var authToken: String? {
        didSet {
            if let token = authToken {
                UserDefaults.standard.set(token, forKey: "auth_token")
            } else {
                UserDefaults.standard.removeObject(forKey: "auth_token")
            }
        }
    }
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)
        
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        
        // Restore saved token
        self.authToken = UserDefaults.standard.string(forKey: "auth_token")
    }
    
    // MARK: - Generic Request
    func request<T: Decodable>(
        _ endpoint: String,
        method: String = "GET",
        body: Encodable? = nil,
        requiresAuth: Bool = true,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        guard var urlComponents = URLComponents(string: "\(APIConfig.baseURL)\(endpoint)") else {
            throw URLError(.badURL)
        }
        
        if let queryItems = queryItems {
            urlComponents.queryItems = queryItems
        }
        
        guard let url = urlComponents.url else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(APIConfig.contentType, forHTTPHeaderField: "Content-Type")
        
        if requiresAuth, let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        if let body = body {
            request.httpBody = try encoder.encode(body)
        }
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            if let errorDetail = try? decoder.decode(APIError.self, from: data) {
                throw NSError(domain: "API", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: errorDetail.detail])
            }
            throw URLError(.badServerResponse)
        }
        
        return try decoder.decode(T.self, from: data)
    }
    
    // MARK: - Multipart Upload
    func uploadFile(
        _ endpoint: String,
        fileURL: URL,
        fileName: String,
        mimeType: String,
        fieldName: String = "file",
        additionalFields: [String: String] = [:]
    ) async throws -> Data {
        let boundary = UUID().uuidString
        var request = URLRequest(url: URL(string: "\(APIConfig.baseURL)\(endpoint)")!)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        var body = Data()
        
        // Add additional fields
        for (key, value) in additionalFields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        
        // Add file
        let fileData = try Data(contentsOf: fileURL)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        
        return data
    }
    
    // MARK: - Streaming (SSE)
    func streamRequest(
        _ endpoint: String,
        method: String = "POST",
        body: Encodable? = nil,
        requiresAuth: Bool = true
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    guard let url = URL(string: "\(APIConfig.baseURL)\(endpoint)") else {
                        throw URLError(.badURL)
                    }
                    
                    var request = URLRequest(url: url)
                    request.httpMethod = method
                    request.setValue("text/plain", forHTTPHeaderField: "Accept")
                    request.setValue(APIConfig.contentType, forHTTPHeaderField: "Content-Type")
                    
                    if requiresAuth, let token = self.authToken {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    
                    if let body = body {
                        request.httpBody = try self.encoder.encode(body)
                    }
                    
                    let (bytes, response) = try await self.session.bytes(for: request)
                    
                    guard let httpResponse = response as? HTTPURLResponse,
                          (200...299).contains(httpResponse.statusCode) else {
                        throw URLError(.badServerResponse)
                    }
                    
                    for try await line in bytes.lines {
                        continuation.yield(line)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
```

---

## 2. Authentication

### Register

```
POST /auth/register
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "John Doe"
}
```

**Swift Implementation:**

```swift
struct RegisterRequest: Codable {
    let email: String
    let password: String
    let name: String?
}

struct Token: Codable {
    let accessToken: String
    let tokenType: String
    let userId: String
    let email: String
    let expiresIn: Int
    
    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case userId = "user_id"
        case email
        case expiresIn = "expires_in"
    }
}

extension NetworkService {
    func register(email: String, password: String, name: String?) async throws -> Token {
        let request = RegisterRequest(email: email, password: password, name: name)
        return try await self.request("/auth/register", method: "POST", body: request, requiresAuth: false)
    }
}
```

**SwiftUI View:**

```swift
import SwiftUI

struct RegisterView: View {
    @StateObject private var network = NetworkService.shared
    @State private var email = ""
    @State private var password = ""
    @State private var name = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var registered = false
    
    var body: some View {
        NavigationView {
            Form {
                Section("Account Details") {
                    TextField("Name", text: $name)
                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                    SecureField("Password", text: $password)
                }
                
                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundColor(.red)
                    }
                }
                
                Section {
                    Button(action: { Task { await register() } }) {
                        if isLoading {
                            ProgressView()
                        } else {
                            Text("Register")
                        }
                    }
                    .disabled(isLoading || email.isEmpty || password.count < 8)
                }
            }
            .navigationTitle("Register")
            .alert("Registered!", isPresented: $registered) {
                Button("OK", role: .cancel) { }
            } message: {
                Text("Check your email for confirmation.")
            }
        }
    }
    
    func register() async {
        isLoading = true
        errorMessage = nil
        do {
            let token = try await network.register(email: email, password: password, name: name)
            if !token.accessToken.isEmpty {
                network.authToken = token.accessToken
            }
            registered = true
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
```

### Login

```
POST /auth/login
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Swift Implementation:**

```swift
struct LoginRequest: Codable {
    let email: String
    let password: String
}

extension NetworkService {
    func login(email: String, password: String) async throws -> Token {
        let request = LoginRequest(email: email, password: password)
        let token: Token = try await self.request("/auth/login", method: "POST", body: request, requiresAuth: false)
        self.authToken = token.accessToken
        return token
    }
}
```

**SwiftUI View:**

```swift
import SwiftUI

struct LoginView: View {
    @StateObject private var network = NetworkService.shared
    @State private var email = ""
    @State private var password = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @Binding var isLoggedIn: Bool
    
    var body: some View {
        NavigationView {
            Form {
                Section("Credentials") {
                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                    SecureField("Password", text: $password)
                }
                
                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundColor(.red)
                    }
                }
                
                Section {
                    Button(action: { Task { await login() } }) {
                        if isLoading {
                            ProgressView()
                        } else {
                            Text("Sign In")
                        }
                    }
                    .disabled(isLoading || email.isEmpty || password.isEmpty)
                }
            }
            .navigationTitle("Sign In")
        }
    }
    
    func login() async {
        isLoading = true
        errorMessage = nil
        do {
            let _ = try await network.login(email: email, password: password)
            isLoggedIn = true
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
```

### Logout

```
POST /auth/logout
```

**Headers:** `Authorization: Bearer <token>`

**Swift:**

```swift
extension NetworkService {
    func logout() async throws {
        let _: [String: String] = try await self.request("/auth/logout", method: "POST")
        self.authToken = nil
    }
}
```

### Get Current User

```
GET /auth/me
```

**Headers:** `Authorization: Bearer <token>`

**Swift:**

```swift
extension NetworkService {
    func getCurrentUser() async throws -> UserResponse {
        return try await self.request("/auth/me")
    }
}
```

### Update User Profile

```
PUT /auth/me
```

**Request Body:**
```json
{
  "name": "John Doe",
  "nickname": "Johnny",
  "claude_api_key": "sk-ant-...",
  "tavily_api_key": "tvly-..."
}
```

**Swift:**

```swift
struct UserUpdate: Codable {
    let name: String?
    let nickname: String?
    let claudeApiKey: String?
    let tavilyApiKey: String?
    
    enum CodingKeys: String, CodingKey {
        case name, nickname
        case claudeApiKey = "claude_api_key"
        case tavilyApiKey = "tavily_api_key"
    }
}

extension NetworkService {
    func updateUser(_ update: UserUpdate) async throws {
        let _: [String: String] = try await self.request("/auth/me", method: "PUT", body: update)
    }
}
```

### Update API Keys

```
PUT /auth/api-keys
```

**Request Body:**
```json
{
  "claude_api_key": "sk-ant-...",
  "tavily_api_key": "tvly-..."
}
```

### Get API Keys Status

```
GET /auth/api-keys
```

**Response:**
```json
{
  "has_claude_key": true,
  "has_tavily_key": false
}
```

### Forgot Password

```
POST /auth/forgot-password
```

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

### Reset Password

```
POST /auth/reset-password
```

**Headers:** `Authorization: Bearer <reset_token>`

**Request Body:**
```json
{
  "new_password": "newSecurePassword123"
}
```

### Change Password

```
PUT /auth/change-password
```

**Request Body:**
```json
{
  "new_password": "newSecurePassword123"
}
```

### Refresh Token

```
POST /auth/refresh-token
```

**Headers:** `Authorization: Bearer <current_token>`

### Admin: List Users

```
GET /auth/admin/users
```

### Admin: Make User Admin

```
POST /auth/admin/users/{user_id}/make-admin
```

### Admin: Revoke Admin

```
POST /auth/admin/users/{user_id}/revoke-admin
```

### Admin: Deactivate User

```
POST /auth/admin/users/{user_id}/deactivate
```

### Admin: Activate User

```
POST /auth/admin/users/{user_id}/activate
```

---

## 3. Chat & Conversations

### List Conversations

```
GET /chat/conversations
```

**Swift:**

```swift
struct Conversation: Codable, Identifiable {
    let id: String
    let userId: String
    let title: String
    let conversationType: String?
    let createdAt: String
    let updatedAt: String
    let isArchived: Bool
    let isPinned: Bool
    let model: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case title
        case conversationType = "conversation_type"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case isArchived = "is_archived"
        case isPinned = "is_pinned"
        case model
    }
}

extension NetworkService {
    func listConversations() async throws -> [Conversation] {
        return try await self.request("/chat/conversations")
    }
}
```

### Create Conversation

```
POST /chat/conversations
```

**Request Body:**
```json
{
  "title": "New Conversation",
  "conversation_type": "agent"
}
```

**Swift:**

```swift
struct CreateConversationRequest: Codable {
    let title: String?
    let conversationType: String?
    
    enum CodingKeys: String, CodingKey {
        case title
        case conversationType = "conversation_type"
    }
}

extension NetworkService {
    func createConversation(title: String? = nil, type: String? = nil) async throws -> Conversation {
        let body = CreateConversationRequest(title: title, conversationType: type)
        return try await self.request("/chat/conversations", method: "POST", body: body)
    }
}
```

### Get Conversation Messages

```
GET /chat/conversations/{conversation_id}/messages
```

**Swift:**

```swift
struct ChatMessage: Codable, Identifiable {
    let id: String
    let conversationId: String
    let role: String
    let content: String
    let createdAt: String
    let metadata: [String: AnyCodable]?
    let artifacts: [[String: AnyCodable]]?
    let toolsUsed: [[String: AnyCodable]]?
    
    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case role, content
        case createdAt = "created_at"
        case metadata, artifacts
        case toolsUsed = "tools_used"
    }
}

// Helper for flexible JSON decoding
struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else {
            value = NSNull()
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let int = value as? Int {
            try container.encode(int)
        } else if let double = value as? Double {
            try container.encode(double)
        } else if let string = value as? String {
            try container.encode(string)
        } else if let bool = value as? Bool {
            try container.encode(bool)
        }
    }
}

extension NetworkService {
    func getMessages(conversationId: String) async throws -> [ChatMessage] {
        return try await self.request("/chat/conversations/\(conversationId)/messages")
    }
}
```

### Rename Conversation

```
PATCH /chat/conversations/{conversation_id}
```

**Request Body:**
```json
{
  "title": "Updated Title"
}
```

### Delete Conversation

```
DELETE /chat/conversations/{conversation_id}
```

### Chat Agent (Streaming)

```
POST /chat/agent
```

This is the **main chat endpoint** with full agent capabilities: tool use, streaming, artifact generation.

**Request Body:**
```json
{
  "content": "Generate a moving average crossover strategy for AAPL",
  "conversation_id": "optional-conversation-id",
  "model": "claude-sonnet-4-6",
  "thinking_mode": "enabled",
  "thinking_budget": 5000,
  "thinking_effort": "medium",
  "skill_slug": null,
  "use_prompt_caching": true,
  "max_iterations": 5,
  "pin_model_version": false
}
```

**Swift Implementation:**

```swift
struct ChatAgentRequest: Codable {
    let content: String
    let conversationId: String?
    let model: String?
    let thinkingMode: String?
    let thinkingBudget: Int?
    let thinkingEffort: String?
    let skillSlug: String?
    let usePromptCaching: Bool
    let maxIterations: Int
    let pinModelVersion: Bool
    
    enum CodingKeys: String, CodingKey {
        case content
        case conversationId = "conversation_id"
        case model
        case thinkingMode = "thinking_mode"
        case thinkingBudget = "thinking_budget"
        case thinkingEffort = "thinking_effort"
        case skillSlug = "skill_slug"
        case usePromptCaching = "use_prompt_caching"
        case maxIterations = "max_iterations"
        case pinModelVersion = "pin_model_version"
    }
}

// MARK: - Chat Streaming ViewModel
@MainActor
class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var currentResponse: String = ""
    @Published var isStreaming = false
    @Published var errorMessage: String?
    @Published var conversationId: String?
    @Published var toolsUsed: [[String: Any]] = []
    @Published var hasArtifacts = false
    
    private let network = NetworkService.shared
    
    func sendMessage(_ content: String, model: String = "claude-sonnet-4-6") async {
        isStreaming = true
        currentResponse = ""
        errorMessage = nil
        toolsUsed = []
        hasArtifacts = false
        
        let request = ChatAgentRequest(
            content: content,
            conversationId: conversationId,
            model: model,
            thinkingMode: nil,
            thinkingBudget: nil,
            thinkingEffort: nil,
            skillSlug: nil,
            usePromptCaching: true,
            maxIterations: 5,
            pinModelVersion: false
        )
        
        do {
            let stream = network.streamRequest("/chat/agent", method: "POST", body: request)
            
            for try await line in stream {
                parseStreamLine(line)
            }
            
            // Save the assistant message
            if !currentResponse.isEmpty {
                let assistantMessage = ChatMessage(
                    id: UUID().uuidString,
                    conversationId: conversationId ?? "",
                    role: "assistant",
                    content: currentResponse,
                    createdAt: ISO8601DateFormatter().string(from: Date()),
                    metadata: nil,
                    artifacts: nil,
                    toolsUsed: nil
                )
                messages.append(assistantMessage)
            }
            
        } catch {
            errorMessage = error.localizedDescription
        }
        
        isStreaming = false
    }
    
    private func parseStreamLine(_ line: String) {
        // Vercel AI SDK Data Stream Protocol:
        // 0:"text chunk"           ← text delta
        // 2:[{...}]                ← data parts
        // 3:"error message"        ← error
        // d:{finishReason, usage}  ← finish message
        
        if line.hasPrefix("0:") {
            // Text delta
            let text = String(line.dropFirst(2))
            // Remove surrounding quotes
            let cleanText = text.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            currentResponse += cleanText
        } else if line.hasPrefix("2:") {
            // Data parts (tool calls, artifacts, file downloads)
            let jsonString = String(line.dropFirst(2))
            if let data = jsonString.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let toolName = json["toolName"] as? String {
                    toolsUsed.append(json)
                    print("🔧 Tool used: \(toolName)")
                }
                if let hasArt = json["has_artifacts"] as? Bool, hasArt {
                    hasArtifacts = true
                }
                if let convId = json["conversation_id"] as? String {
                    conversationId = convId
                }
            }
        } else if line.hasPrefix("3:") {
            // Error
            let errorMsg = String(line.dropFirst(2))
            errorMessage = errorMsg.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        } else if line.hasPrefix("d:") {
            // Finish message
            let jsonString = String(line.dropFirst(2))
            if let data = jsonString.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let usage = json["usage"] as? [String: Any] {
                    print("📊 Token usage: \(usage)")
                }
            }
        }
    }
}
```

**SwiftUI Chat View:**

```swift
import SwiftUI

struct ChatView: View {
    @StateObject private var viewModel = ChatViewModel()
    @State private var inputText = ""
    @State private var selectedModel = "claude-sonnet-4-6"
    
    let models = [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-sonnet-4-5",
        "claude-opus-4-5"
    ]
    
    var body: some View {
        VStack {
            // Model Picker
            Picker("Model", selection: $selectedModel) {
                ForEach(models, id: \.self) { model in
                    Text(model).tag(model)
                }
            }
            .pickerStyle(.menu)
            .padding(.horizontal)
            
            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(viewModel.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                        
                        // Streaming response
                        if viewModel.isStreaming && !viewModel.currentResponse.isEmpty {
                            MessageBubble(message: ChatMessage(
                                id: "streaming",
                                conversationId: "",
                                role: "assistant",
                                content: viewModel.currentResponse,
                                createdAt: "",
                                metadata: nil,
                                artifacts: nil,
                                toolsUsed: nil
                            ))
                            .id("streaming")
                        }
                        
                        // Tool indicators
                        if !viewModel.toolsUsed.isEmpty {
                            ToolIndicatorsView(tools: viewModel.toolsUsed)
                        }
                    }
                    .padding()
                }
                .onChange(of: viewModel.currentResponse) { _ in
                    withAnimation {
                        proxy.scrollTo("streaming", anchor: .bottom)
                    }
                }
            }
            
            // Error
            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundColor(.red)
                    .padding(.horizontal)
            }
            
            // Input
            HStack {
                TextField("Type a message...", text: $inputText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await sendMessage() } }
                
                Button(action: { Task { await sendMessage() } }) {
                    if viewModel.isStreaming {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                    }
                }
                .disabled(inputText.isEmpty || viewModel.isStreaming)
            }
            .padding()
        }
        .navigationTitle("Chat")
    }
    
    func sendMessage() async {
        let message = inputText
        inputText = ""
        
        // Add user message
        viewModel.messages.append(ChatMessage(
            id: UUID().uuidString,
            conversationId: viewModel.conversationId ?? "",
            role: "user",
            content: message,
            createdAt: ISO8601DateFormatter().string(from: Date()),
            metadata: nil,
            artifacts: nil,
            toolsUsed: nil
        ))
        
        await viewModel.sendMessage(message, model: selectedModel)
    }
}

struct MessageBubble: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.role == "user" { Spacer() }
            
            VStack(alignment: message.role == "user" ? .trailing : .leading) {
                Text(message.content)
                    .padding(12)
                    .background(message.role == "user" ? Color.blue : Color.gray.opacity(0.2))
                    .foregroundColor(message.role == "user" ? .white : .primary)
                    .cornerRadius(16)
                
                Text(message.role.capitalized)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            
            if message.role == "assistant" { Spacer() }
        }
    }
}

struct ToolIndicatorsView: View {
    let tools: [[String: Any]]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(0..<tools.count, id: \.self) { index in
                if let toolName = tools[index]["toolName"] as? String {
                    Label(toolName, systemImage: "wrench.and.screwdriver")
                        .font(.caption)
                        .foregroundColor(.orange)
                }
            }
        }
        .padding(8)
        .background(Color.orange.opacity(0.1))
        .cornerRadius(8)
    }
}
```

### List Available Models

```
GET /chat/models
```

**Swift:**

```swift
struct ModelsResponse: Codable {
    let models: [String: [String]]
    let default: String
    let userHasKeys: [String: Bool]
    
    enum CodingKeys: String, CodingKey {
        case models
        case `default`
        case userHasKeys = "user_has_keys"
    }
}

extension NetworkService {
    func listModels() async throws -> ModelsResponse {
        return try await self.request("/chat/models")
    }
}
```

### Text-to-Speech

```
POST /chat/tts
```

**Request Body:**
```json
{
  "text": "Hello, this is a test.",
  "voice": "en-US-AriaNeural"
}
```

**Response:** MP3 audio stream

**Swift:**

```swift
struct TTSRequest: Codable {
    let text: String
    let voice: String
}

extension NetworkService {
    func textToSpeech(text: String, voice: String = "en-US-AriaNeural") async throws -> Data {
        let body = TTSRequest(text: text, voice: voice)
        var request = URLRequest(url: URL(string: "\(APIConfig.baseURL)/chat/tts")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try encoder.encode(body)
        
        let (data, _) = try await session.data(for: request)
        return data
    }
}
```

### List TTS Voices

```
GET /chat/tts/voices
```

**Swift:**

```swift
struct TTSVoice: Codable, Identifiable {
    let name: String
    let gender: String
    let locale: String
    
    var id: String { name }
}

struct TTSVoicesResponse: Codable {
    let voices: [TTSVoice]
    let count: Int
}

extension NetworkService {
    func listTTSVoices() async throws -> TTSVoicesResponse {
        return try await self.request("/chat/tts/voices", requiresAuth: false)
    }
}
```

---

## 4. AI SDK Streaming

### AI Status

```
GET /ai/status
```

**Swift:**

```swift
struct AIStatus: Codable {
    let status: String
    let skillsAvailable: Int
    let streamProtocol: String
    
    enum CodingKeys: String, CodingKey {
        case status
        case skillsAvailable = "skills_available"
        case streamProtocol = "stream_protocol"
    }
}

extension NetworkService {
    func aiStatus() async throws -> AIStatus {
        return try await self.request("/ai/status", requiresAuth: false)
    }
}
```

### List Invokable Skills

```
GET /ai/skills
```

### Get Invokable Skill Detail

```
GET /ai/skills/{slug}
```

### Invoke Skill (Streaming)

```
POST /ai/skills/{slug}
```

**Request Body:**
```json
{
  "message": "Create a quarterly performance report for Q3 2025",
  "system_prompt": null,
  "extra_context": "",
  "conversation_history": null,
  "max_tokens": null
}
```

**Swift:**

```swift
struct SkillInvokeRequest: Codable {
    let message: String
    let systemPrompt: String?
    let extraContext: String
    let conversationHistory: [[String: String]]?
    let maxTokens: Int?
    
    enum CodingKeys: String, CodingKey {
        case message
        case systemPrompt = "system_prompt"
        case extraContext = "extra_context"
        case conversationHistory = "conversation_history"
        case maxTokens = "max_tokens"
    }
}

extension NetworkService {
    func invokeSkill(slug: String, message: String, extraContext: String = "") -> AsyncThrowingStream<String, Error> {
        let body = SkillInvokeRequest(
            message: message,
            systemPrompt: nil,
            extraContext: extraContext,
            conversationHistory: nil,
            maxTokens: nil
        )
        return streamRequest("/ai/skills/\(slug)", method: "POST", body: body)
    }
}
```

**SwiftUI Streaming View:**

```swift
struct SkillInvocationView: View {
    let skillSlug: String
    let message: String
    
    @StateObject private var network = NetworkService.shared
    @State private var response = ""
    @State private var isStreaming = false
    @State private var error: String?
    
    var body: some View {
        VStack(alignment: .leading) {
            Text("Running: \(skillSlug)")
                .font(.headline)
            
            ScrollView {
                Text(response)
                    .font(.system(.body, design: .monospaced))
                    .padding()
            }
            
            if let error = error {
                Text(error)
                    .foregroundColor(.red)
            }
        }
        .task {
            await streamSkill()
        }
    }
    
    func streamSkill() async {
        isStreaming = true
        response = ""
        
        let stream = network.invokeSkill(slug: skillSlug, message: message)
        
        do {
            for try await line in stream {
                // Parse Vercel AI SDK stream protocol
                if line.hasPrefix("0:") {
                    let text = String(line.dropFirst(2))
                    response += text.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
                } else if line.hasPrefix("3:") {
                    error = String(line.dropFirst(2))
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
        
        isStreaming = false
    }
}
```

---

## 5. AFL Code Generation

### Generate AFL

```
POST /afl/generate
```

**Request Body:**
```json
{
  "prompt": "Create a moving average crossover strategy with RSI filter for daily charts",
  "strategy_type": "standalone",
  "backtest_settings": {
    "initial_equity": 100000,
    "position_size": "100",
    "max_positions": 10,
    "commission": 0.0005,
    "trade_delays": [0, 0, 0, 0],
    "margin_requirement": 100
  },
  "conversation_id": null,
  "answers": null,
  "stream": false,
  "uploaded_file_ids": null,
  "kb_context": null,
  "thinking_mode": "enabled",
  "thinking_budget": 5000
}
```

**Swift:**

```swift
struct BacktestSettingsInput: Codable {
    let initialEquity: Double
    let positionSize: String
    let maxPositions: Int
    let commission: Double
    let tradeDelays: [Int]
    let marginRequirement: Double
    
    enum CodingKeys: String, CodingKey {
        case initialEquity = "initial_equity"
        case positionSize = "position_size"
        case maxPositions = "max_positions"
        case commission
        case tradeDelays = "trade_delays"
        case marginRequirement = "margin_requirement"
    }
}

struct AFLGenerateRequest: Codable {
    let prompt: String
    let strategyType: String
    let backtestSettings: BacktestSettingsInput?
    let conversationId: String?
    let answers: [String: String]?
    let stream: Bool
    let uploadedFileIds: [String]?
    let kbContext: String?
    let thinkingMode: String?
    let thinkingBudget: Int?
    
    enum CodingKeys: String, CodingKey {
        case prompt
        case strategyType = "strategy_type"
        case backtestSettings = "backtest_settings"
        case conversationId = "conversation_id"
        case answers
        case stream
        case uploadedFileIds = "uploaded_file_ids"
        case kbContext = "kb_context"
        case thinkingMode = "thinking_mode"
        case thinkingBudget = "thinking_budget"
    }
}

struct AFLGenerateResponse: Codable {
    let code: String
    let aflCode: String?
    let explanation: String?
    let stats: [String: AnyCodable]?
    
    enum CodingKeys: String, CodingKey {
        case code
        case aflCode = "afl_code"
        case explanation
        case stats
    }
}

extension NetworkService {
    func generateAFL(prompt: String, strategyType: String = "standalone", stream: Bool = false) async throws -> AFLGenerateRequest {
        let body = AFLGenerateRequest(
            prompt: prompt,
            strategyType: strategyType,
            backtestSettings: nil,
            conversationId: nil,
            answers: nil,
            stream: stream,
            uploadedFileIds: nil,
            kbContext: nil,
            thinkingMode: nil,
            thinkingBudget: nil
        )
        
        if stream {
            // Handle streaming
            let streamResult = streamRequest("/afl/generate", method: "POST", body: body)
            // Process SSE stream...
            return body
        } else {
            return try await self.request("/afl/generate", method: "POST", body: body)
        }
    }
}
```

### Optimize AFL

```
POST /afl/optimize
```

**Request Body:**
```json
{
  "code": "// existing AFL code here"
}
```

### Debug AFL

```
POST /afl/debug
```

**Request Body:**
```json
{
  "code": "// AFL code with errors",
  "error_message": "Error: Unknown function 'RSI'"
}
```

### Explain AFL

```
POST /afl/explain
```

**Request Body:**
```json
{
  "code": "// AFL code to explain"
}
```

### Validate AFL

```
POST /afl/validate
```

**Request Body:**
```json
{
  "code": "// AFL code to validate"
}
```

### List AFL Codes

```
GET /afl/codes?limit=50
```

### Get AFL Code

```
GET /afl/codes/{code_id}
```

### Delete AFL Code

```
DELETE /afl/codes/{code_id}
```

### AFL History

```
POST /afl/history          # Save to history
GET  /afl/history          # Get history
DELETE /afl/history/{id}   # Delete history entry
```

### Upload AFL File

```
POST /afl/upload
```

**Swift (Multipart Upload):**

```swift
extension NetworkService {
    func uploadAFLFile(fileURL: URL, fileName: String) async throws -> [String: Any] {
        let data = try await uploadFile(
            "/afl/upload",
            fileURL: fileURL,
            fileName: fileName,
            mimeType: "text/csv"
        )
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
}
```

### List Uploaded Files

```
GET /afl/files
```

### Get File Details

```
GET /afl/files/{file_id}
```

### Delete Uploaded File

```
DELETE /afl/files/{file_id}
```

### Settings Presets

```
POST   /afl/settings/presets                    # Save preset
GET    /afl/settings/presets                    # List presets
GET    /afl/settings/presets/{preset_id}        # Get preset
PUT    /afl/settings/presets/{preset_id}        # Update preset
DELETE /afl/settings/presets/{preset_id}        # Delete preset
POST   /afl/settings/presets/{preset_id}/set-default  # Set as default
```

**Swift:**

```swift
struct SettingsPreset: Codable, Identifiable {
    let id: String?
    let name: String
    let settings: BacktestSettingsInput
    let isDefault: Bool
    
    enum CodingKeys: String, CodingKey {
        case id, name, settings
        case isDefault = "is_default"
    }
}

extension NetworkService {
    func saveSettingsPreset(_ preset: SettingsPreset) async throws -> SettingsPreset {
        return try await self.request("/afl/settings/presets", method: "POST", body: preset)
    }
    
    func getSettingsPresets() async throws -> [SettingsPreset] {
        return try await self.request("/afl/settings/presets")
    }
}
```

---

## 6. Knowledge Base / Brain

### Upload Document

```
POST /brain/upload
```

**Swift (Multipart):**

```swift
extension NetworkService {
    func uploadDocument(fileURL: URL, fileName: String, title: String? = nil, category: String = "general") async throws -> [String: Any] {
        var fields: [String: String] = ["category": category]
        if let title = title {
            fields["title"] = title
        }
        let data = try await uploadFile(
            "/brain/upload",
            fileURL: fileURL,
            fileName: fileName,
            mimeType: "application/octet-stream",
            additionalFields: fields
        )
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
}
```

### Batch Upload

```
POST /brain/upload-batch
```

### Upload Text

```
POST /brain/upload-text
```

**Request Body:**
```json
{
  "title": "Trading Rules",
  "content": "Always use stop losses...",
  "category": "strategy"
}
```

### Search Knowledge Base

```
POST /brain/search
```

**Request Body:**
```json
{
  "query": "moving average strategy",
  "category": "strategy",
  "limit": 10
}
```

### List Documents

```
GET /brain/documents?category=strategy&limit=50
```

### Get Document

```
GET /brain/documents/{document_id}
```

### Get Document Content (Binary)

```
GET /brain/documents/{document_id}/content
```

### Download Document

```
GET /brain/documents/{document_id}/download
```

### Delete Document

```
DELETE /brain/documents/{document_id}
```

### Knowledge Base Stats

```
GET /brain/stats
```

**Response:**
```json
{
  "total_documents": 42,
  "total_size": 15000000,
  "total_size_on_disk_mb": 14.3,
  "total_chunks": 500,
  "total_learnings": 10,
  "categories": {
    "strategy": 15,
    "research": 12,
    "general": 15
  }
}
```

---

## 7. File Upload

### Direct Upload

```
POST /upload/direct
```

**Swift (Multipart):**

```swift
struct FileInfo: Codable, Identifiable {
    let id: String
    let userId: String
    let storagePath: String
    let originalFilename: String
    let contentType: String?
    let fileSize: Int?
    let status: String
    let contentHash: String?
    let createdAt: String
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case storagePath = "storage_path"
        case originalFilename = "original_filename"
        case contentType = "content_type"
        case fileSize = "file_size"
        case status
        case contentHash = "content_hash"
        case createdAt = "created_at"
    }
}

extension NetworkService {
    func uploadFileDirect(fileURL: URL, fileName: String, mimeType: String) async throws -> FileInfo {
        let data = try await uploadFile(
            "/upload/direct",
            fileURL: fileURL,
            fileName: fileName,
            mimeType: mimeType
        )
        return try decoder.decode(FileInfo.self, from: data)
    }
}
```

### Upload to Conversation

```
POST /upload/conversations/{conversation_id}
```

### List Files

```
GET /upload/files?limit=50&offset=0
```

### Get File Info

```
GET /upload/files/{file_id}
```

### Download File

```
GET /upload/files/{file_id}/download
```

### Delete File

```
DELETE /upload/files/{file_id}
```

### Extract Text

```
POST /upload/files/{file_id}/extract
```

### Get Conversation Files

```
GET /upload/conversations/{conversation_id}/files
```

### Link File to Conversation

```
POST /upload/files/{file_id}/link/{conversation_id}
```

### Storage Info

```
GET /upload/info
```

---

## 8. Generated Files

### Download Generated File

```
GET /files/{file_id}/download
```

### Get File Info

```
GET /files/{file_id}/info
```

### List Generated Files

```
GET /files/generated
```

---

## 9. Backtest Analysis

### Upload Backtest Results

```
POST /backtest/upload
```

**Swift (Multipart):**

```swift
extension NetworkService {
    func uploadBacktest(fileURL: URL, fileName: String, strategyId: String? = nil) async throws -> [String: Any] {
        var fields: [String: String] = [:]
        if let strategyId = strategyId {
            fields["strategy_id"] = strategyId
        }
        let data = try await uploadFile(
            "/backtest/upload",
            fileURL: fileURL,
            fileName: fileName,
            mimeType: "text/csv",
            additionalFields: fields
        )
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
}
```

### List Backtests

```
GET /backtest/history
```

### Get Backtest

```
GET /backtest/{backtest_id}
```

### Get Strategy Backtests

```
GET /backtest/strategy/{strategy_id}
```

---

## 10. Researcher

### Company Research

```
GET /researcher/company/{symbol}
```

**Swift:**

```swift
struct CompanyResearch: Codable {
    let success: Bool
    let data: [String: AnyCodable]
    let message: String
}

extension NetworkService {
    func getCompanyResearch(symbol: String) async throws -> CompanyResearch {
        return try await self.request("/researcher/company/\(symbol)")
    }
}
```

### Company Research (Streaming)

```
GET /researcher/company/{symbol}/stream
```

### Company News

```
GET /researcher/news/{symbol}?limit=20
```

### Strategy Analysis

```
POST /researcher/strategy-analysis
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "strategy_type": "momentum",
  "timeframe": "daily"
}
```

### Peer Comparison

```
POST /researcher/comparison
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "peers": ["MSFT", "GOOGL", "AMZN"]
}
```

### Macro Context

```
GET /researcher/macro-context
```

### SEC Filings

```
GET /researcher/sec-filings/{symbol}
```

### Generate Research Report

```
POST /researcher/generate-report
```

**Request Body:**
```json
{
  "symbol": "AAPL",
  "report_type": "company",
  "sections": ["executive_summary", "fundamental_analysis"],
  "format": "pdf"
}
```

### Export Report

```
GET /researcher/reports/{report_id}/export?format=pdf
```

### Search Research

```
GET /researcher/search?query=AAPL&search_type=company&limit=10
```

### Trending Research

```
GET /researcher/trending?limit=10
```

### Researcher Health

```
GET /researcher/health
```

---

## 11. Skills

### List Skills

```
GET /skills?category=market_analysis&include_builtins=true
```

**Swift:**

```swift
struct Skill: Codable, Identifiable {
    let skillId: String
    let name: String
    let slug: String
    let description: String
    let category: String
    let maxTokens: Int
    let tags: [String]
    let enabled: Bool
    let supportsStreaming: Bool
    let isBuiltin: Bool
    
    enum CodingKeys: String, CodingKey {
        case skillId = "skill_id"
        case name, slug, description, category
        case maxTokens = "max_tokens"
        case tags, enabled
        case supportsStreaming = "supports_streaming"
        case isBuiltin = "is_builtin"
    }
    
    var id: String { slug }
}

struct SkillsResponse: Codable {
    let skills: [Skill]
    let count: Int
}

extension NetworkService {
    func listSkills(category: String? = nil) async throws -> SkillsResponse {
        var queryItems: [URLQueryItem] = []
        if let category = category {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        return try await self.request("/skills", queryItems: queryItems.isEmpty ? nil : queryItems)
    }
}
```

### List Skill Categories

```
GET /skills/categories
```

### Get Skill Detail

```
GET /skills/{slug}
```

### List Skill Jobs

```
GET /skills/jobs
```

---

## 12. YFinance Data

### Get Comprehensive Data

```
GET /yfinance/{ticker}?include=info,history&history_period=1y&history_interval=1d
```

**Swift:**

```swift
struct YFinanceResponse: Codable {
    let ticker: String
    let timestamp: String
    let data: [String: AnyCodable]
    let metadata: YFinanceMetadata
    let summary: YFinanceSummary
    
    struct YFinanceMetadata: Codable {
        let requestedCategories: [String]
        let historyPeriod: String
        let historyInterval: String
        
        enum CodingKeys: String, CodingKey {
            case requestedCategories = "requested_categories"
            case historyPeriod = "history_period"
            case historyInterval = "history_interval"
        }
    }
    
    struct YFinanceSummary: Codable {
        let totalCategoriesRequested: Int
        let categoriesSuccessfullyFetched: Int
        let categoriesWithErrors: Int
        
        enum CodingKeys: String, CodingKey {
            case totalCategoriesRequested = "total_categories_requested"
            case categoriesSuccessfullyFetched = "categories_successfully_fetched"
            case categoriesWithErrors = "categories_with_errors"
        }
    }
}

extension NetworkService {
    func getYFinanceData(ticker: String, include: [String]? = nil, historyPeriod: String = "1y", historyInterval: String = "1d") async throws -> YFinanceResponse {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "history_period", value: historyPeriod),
            URLQueryItem(name: "history_interval", value: historyInterval)
        ]
        if let include = include {
            queryItems.append(URLQueryItem(name: "include", value: include.joined(separator: ",")))
        }
        return try await self.request("/yfinance/\(ticker)", queryItems: queryItems)
    }
}
```

### Get Summary

```
GET /yfinance/{ticker}/summary
```

### Get History

```
GET /yfinance/{ticker}/history?period=1y&interval=1d
```

**Available Categories:**
`info`, `history`, `actions`, `calendar`, `dividends`, `splits`, `capital_gains`, `shares`, `fast_info`, `recommendations`, `recommendations_summary`, `upgrades_downgrades`, `earnings`, `quarterly_earnings`, `income_stmt`, `quarterly_income_stmt`, `ttm_income_stmt`, `balance_sheet`, `quarterly_balance_sheet`, `cash_flow`, `quarterly_cash_flow`, `ttm_cash_flow`, `analyst_price_targets`, `earnings_estimate`, `revenue_estimate`, `earnings_history`, `eps_trend`, `eps_revisions`, `growth_estimates`, `sustainability`, `options`, `news`, `earnings_dates`, `history_metadata`, `major_holders`, `institutional_holders`, `mutualfund_holders`, `insider_purchases`, `insider_transactions`, `insider_roster_holders`

**Available Periods:** `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max`

**Available Intervals:** `1m`, `2m`, `5m`, `15m`, `30m`, `60m`, `90m`, `1h`, `1d`, `5d`, `1wk`, `1mo`, `3mo`

---

## 13. SEC EDGAR

### Security ID Lookup

```
GET /edgar/security/{identifier}
```

**Swift:**

```swift
extension NetworkService {
    func getSecurityId(identifier: String) async throws -> [String: Any] {
        let data: [String: AnyCodable] = try await self.request("/edgar/security/\(identifier)")
        return data.mapValues { $0.value }
    }
}
```

### Search Companies

```
GET /edgar/search?q=Apple&limit=10
```

### Company Info

```
GET /edgar/company/{cik}
```

### Company Filings

```
GET /edgar/company/{cik}/filings?form_type=10-K&limit=20&offset=0
```

### Filing Documents

```
GET /edgar/company/{cik}/filings/{accession_number}
```

### Key Financials

```
GET /edgar/company/{cik}/financials
```

### XBRL Concept Time Series

```
GET /edgar/company/{cik}/concept?concept=Revenues&taxonomy=us-gaap&limit=20
```

### Ticker Shortcuts

```
GET /edgar/ticker/{ticker}/filings          # All filings
GET /edgar/ticker/{ticker}/annual           # 10-K filings
GET /edgar/ticker/{ticker}/quarterly        # 10-Q filings
GET /edgar/ticker/{ticker}/events           # 8-K filings
GET /edgar/ticker/{ticker}/insider          # Form 4 filings
GET /edgar/ticker/{ticker}/proxy            # DEF 14A filings
GET /edgar/ticker/{ticker}/financials       # Key XBRL financials
```

### Full-Text Search

```
POST /edgar/search/fulltext
```

**Request Body:**
```json
{
  "query": "AI AND revenue AND guidance",
  "form_type": "10-K",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "limit": 10
}
```

### All Tickers Reference

```
GET /edgar/tickers?exchange=Nasdaq&limit=100&offset=0
```

---

## 14. Background Tasks

### Submit Task

```
POST /tasks
```

**Request Body:**
```json
{
  "task_type": "document",
  "title": "Generate Q3 Report",
  "conversation_id": "optional-id",
  "skill_slug": "potomac-docx-skill",
  "message": "Create a quarterly performance report",
  "params": {
    "skill_slug": "potomac-docx-skill"
  }
}
```

**Swift:**

```swift
struct TaskSubmitRequest: Codable {
    let taskType: String
    let title: String
    let conversationId: String?
    let skillSlug: String?
    let message: String
    let params: [String: String]?
    
    enum CodingKeys: String, CodingKey {
        case taskType = "task_type"
        case title
        case conversationId = "conversation_id"
        case skillSlug = "skill_slug"
        case message
        case params
    }
}

struct TaskResponse: Codable, Identifiable {
    let id: String
    let userId: String
    let title: String
    let taskType: String
    let status: String
    let progress: Int
    let message: String
    let result: [String: AnyCodable]?
    let error: String?
    let createdAt: Double
    let startedAt: Double?
    let completedAt: Double?
    let elapsedSeconds: Double
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case title
        case taskType = "task_type"
        case status, progress, message, result, error
        case createdAt = "created_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case elapsedSeconds = "elapsed_seconds"
    }
}

extension NetworkService {
    func submitTask(_ request: TaskSubmitRequest) async throws -> [String: Any] {
        let data: [String: AnyCodable] = try await self.request("/tasks", method: "POST", body: request)
        return data.mapValues { $0.value }
    }
    
    func listTasks() async throws -> [TaskResponse] {
        let response: [String: [TaskResponse]] = try await self.request("/tasks")
        return response["tasks"] ?? []
    }
    
    func getTask(taskId: String) async throws -> TaskResponse {
        let response: [String: TaskResponse] = try await self.request("/tasks/\(taskId)")
        return response["task"] ?? TaskResponse(
            id: "", userId: "", title: "", taskType: "",
            status: "unknown", progress: 0, message: "",
            result: nil, error: nil, createdAt: 0,
            startedAt: nil, completedAt: nil, elapsedSeconds: 0
        )
    }
}
```

### List Tasks

```
GET /tasks
```

### Get Task Status

```
GET /tasks/{task_id}
```

### Cancel Task

```
POST /tasks/{task_id}/cancel
```

### Dismiss Task

```
DELETE /tasks/{task_id}
```

### Clear Completed Tasks

```
DELETE /tasks
```

**SwiftUI Task Manager View:**

```swift
struct TaskManagerView: View {
    @StateObject private var network = NetworkService.shared
    @State private var tasks: [TaskResponse] = []
    @State private var isLoading = false
    
    var body: some View {
        List {
            Section("Active Tasks") {
                ForEach(tasks.filter { $0.status == "running" || $0.status == "pending" }) { task in
                    TaskRowView(task: task)
                }
            }
            
            Section("Completed") {
                ForEach(tasks.filter { $0.status == "complete" || $0.status == "failed" }) { task in
                    TaskRowView(task: task)
                }
            }
        }
        .navigationTitle("Tasks")
        .refreshable { await loadTasks() }
        .task { await loadTasks() }
    }
    
    func loadTasks() async {
        isLoading = true
        do {
            tasks = try await network.listTasks()
        } catch {
            print("Failed to load tasks: \(error)")
        }
        isLoading = false
    }
}

struct TaskRowView: View {
    let task: TaskResponse
    
    var body: some View {
        VStack(alignment: .leading) {
            Text(task.title)
                .font(.headline)
            
            HStack {
                Text(task.status.capitalized)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(statusColor.opacity(0.2))
                    .foregroundColor(statusColor)
                    .cornerRadius(4)
                
                if task.status == "running" {
                    ProgressView(value: Double(task.progress) / 100)
                        .progressViewStyle(.linear)
                }
            }
            
            if !task.message.isEmpty {
                Text(task.message)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }
    
    var statusColor: Color {
        switch task.status {
        case "complete": return .green
        case "running": return .blue
        case "pending": return .orange
        case "failed": return .red
        default: return .gray
        }
    }
}
```

---

## 15. Consensus

### Validate Consensus

```
POST /consensus/validate
```

**Request Body:**
```json
{
  "messages": [
    {"role": "user", "content": "What is the best trading strategy for volatile markets?"}
  ],
  "models": [
    {"model_id": "claude-sonnet-4-6", "provider": "anthropic"},
    {"model_id": "gpt-4o", "provider": "openai"}
  ],
  "max_tokens": 1024,
  "majority_threshold": 0.5
}
```

**Swift:**

```swift
struct ConsensusMessage: Codable {
    let role: String
    let content: String
}

struct ConsensusModelConfig: Codable {
    let modelId: String
    let provider: String
    let apiKey: String?
    
    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case provider
        case apiKey = "api_key"
    }
}

struct ConsensusRequest: Codable {
    let messages: [ConsensusMessage]
    let models: [ConsensusModelConfig]
    let maxTokens: Int
    let majorityThreshold: Double
    
    enum CodingKeys: String, CodingKey {
        case messages, models
        case maxTokens = "max_tokens"
        case majorityThreshold = "majority_threshold"
    }
}

extension NetworkService {
    func runConsensus(_ request: ConsensusRequest) async throws -> [String: Any] {
        let data: [String: AnyCodable] = try await self.request("/consensus/validate", method: "POST", body: request)
        return data.mapValues { $0.value }
    }
    
    func getConsensusModels() async throws -> [String: Any] {
        let data: [String: AnyCodable] = try await self.request("/consensus/models")
        return data.mapValues { $0.value }
    }
}
```

### Get Consensus Models

```
GET /consensus/models
```

---

## 16. Training

### Submit Feedback

```
POST /train/feedback
```

**Request Body:**
```json
{
  "code_id": "optional-code-id",
  "original_prompt": "Create a MACD strategy",
  "generated_code": "// AFL code",
  "feedback_type": "correction",
  "feedback_text": "The MACD signal should use 12,26,9 parameters",
  "correct_code": "// corrected AFL code",
  "rating": 3
}
```

### Get My Feedback

```
GET /train/feedback/my?limit=50
```

### Get Feedback Detail

```
GET /train/feedback/{feedback_id}
```

### Test Training

```
POST /train/test
```

**Request Body:**
```json
{
  "prompt": "Create an RSI strategy",
  "category": "afl",
  "include_training": true
}
```

### Get Training Effectiveness

```
GET /train/effectiveness
```

### Suggest Training

```
POST /train/suggest
```

**Request Body:**
```json
{
  "title": "Better RSI Calculation",
  "description": "Use Wilder's smoothing for RSI",
  "example_input": "Calculate RSI with proper smoothing",
  "example_output": "RSI = 100 - (100 / (1 + RS))",
  "reason": "Standard RSI uses Wilder's smoothing"
}
```

### Get My Suggestions

```
GET /train/suggestions/my?limit=50
```

### Quick Learn

```
POST /train/quick-learn
```

**Request Body (Form):**
- `code`: The code example
- `explanation`: What it demonstrates

### Learning Curve

```
GET /train/analytics/learning-curve?days=30
```

### Popular Patterns

```
GET /train/analytics/popular-patterns?limit=10
```

### Search Training Knowledge

```
GET /train/knowledge/search?query=RSI&category=afl&limit=10
```

### Training Categories

```
GET /train/knowledge/categories
```

### Training Types

```
GET /train/knowledge/types
```

### Training Stats

```
GET /train/stats
```

---

## 17. Admin

> **Note:** Admin endpoints require the user to have `is_admin: true` in their profile.

### Admin Status

```
GET /admin/status
```

### Make User Admin

```
POST /admin/make-admin/{target_user_id}
```

### Revoke Admin

```
POST /admin/revoke-admin/{target_user_id}
```

### Training Management

```
POST   /admin/train                           # Add training example
POST   /admin/train/quick                     # Quick train
POST   /admin/train/correction                # Add correction
POST   /admin/train/batch                     # Batch import
GET    /admin/training                        # List training
GET    /admin/training/{id}                   # Get training
PUT    /admin/training/{id}                   # Update training
DELETE /admin/training/{id}                   # Delete training
POST   /admin/training/{id}/toggle            # Toggle active
GET    /admin/training/stats/overview          # Training stats
GET    /admin/training/export/all             # Export training
GET    /admin/training/context/preview        # Preview context
```

### User Management

```
GET    /admin/users                           # List users
GET    /admin/users/{user_id}                 # Get user
PUT    /admin/users/{user_id}                 # Update user
DELETE /admin/users/{user_id}                 # Delete user (soft)
POST   /admin/users/{user_id}/restore         # Restore user
```

### System Configuration

```
GET  /admin/config                            # Get config
PUT  /admin/config                            # Update config
POST /admin/config/add-admin-email            # Add admin email
```

### Feedback Review

```
GET  /admin/feedback                          # List all feedback
GET  /admin/feedback/{id}                     # Get feedback detail
POST /admin/feedback/{id}/review              # Review feedback
```

### Training Suggestions Review

```
GET  /admin/suggestions                       # List suggestions
GET  /admin/suggestions/{id}                  # Get suggestion detail
POST /admin/suggestions/{id}/review           # Review suggestion
POST /admin/suggestions/{id}/approve          # Quick approve
POST /admin/suggestions/{id}/reject           # Quick reject
```

### Analytics

```
GET /admin/analytics/overview?days=30
GET /admin/analytics/trends?days=30
GET /admin/analytics/engagement?days=30
```

### Audit Logs

```
GET /admin/audit-logs?action_type=make_admin&limit=100&offset=0
```

### System Health

```
GET /admin/health/system
```

### Toggle Maintenance

```
POST /admin/maintenance/toggle?enable=true
```

### Export Data

```
GET /admin/export/users
GET /admin/export/feedback?status=pending_review
GET /admin/export/training?training_type=rule&category=afl
```

---

## 18. Presentation Generation

### Generate Presentation

```
POST /api/generate-presentation
```

**Request Body:**
```json
{
  "title": "Q3 2025 Performance Report",
  "slides": [
    {
      "title": "Executive Summary",
      "content": [
        {
          "type": "text",
          "x": 100,
          "y": 100,
          "width": 600,
          "height": 100,
          "content": "Portfolio returned 12.5% YTD",
          "style": {
            "fontSize": 32,
            "fontWeight": "bold",
            "fontFamily": "Rajdhani",
            "color": "#212121",
            "textAlign": "center"
          }
        }
      ],
      "layout": "title",
      "background": "#FFFFFF"
    }
  ],
  "theme": "potomac",
  "format": "pptx"
}
```

**Response:** Binary PPTX file

**Swift:**

```swift
struct PresentationRequest: Codable {
    let title: String
    let slides: [SlideData]
    let theme: String
    let format: String
}

struct SlideData: Codable {
    let title: String
    let content: [SlideElement]
    let layout: String
    let background: String
    let notes: String?
}

struct SlideElement: Codable {
    let type: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let content: ElementContent
    let style: [String: AnyCodable]?
}

struct ElementContent: Codable {
    let type: String?
    let src: String?
    let alt: String?
    let data: [String: AnyCodable]?
    let config: [String: AnyCodable]?
    let headers: [String]?
    let rows: [[String]]?
    
    // For text type
    let text: String?
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decodeIfPresent(String.self, forKey: .type)
        src = try container.decodeIfPresent(String.self, forKey: .src)
        alt = try container.decodeIfPresent(String.self, forKey: .alt)
        data = try container.decodeIfPresent([String: AnyCodable].self, forKey: .data)
        config = try container.decodeIfPresent([String: AnyCodable].self, forKey: .config)
        headers = try container.decodeIfPresent([String].self, forKey: .headers)
        rows = try container.decodeIfPresent([[String]].self, forKey: .rows)
        text = try container.decodeIfPresent(String.self, forKey: .text)
    }
    
    enum CodingKeys: String, CodingKey {
        case type, src, alt, data, config, headers, rows, text
    }
}

extension NetworkService {
    func generatePresentation(_ request: PresentationRequest) async throws -> Data {
        let encoder = JSONEncoder()
        let body = try encoder.encode(request)
        
        var urlRequest = URLRequest(url: URL(string: "\(APIConfig.baseURL)/api/generate-presentation")!)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = authToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        urlRequest.httpBody = body
        
        let (data, response) = try await session.data(for: urlRequest)
        
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        
        return data
    }
}
```

### Test Presentation

```
POST /api/generate-presentation/test
```

---

## 19. KB Admin Bulk Upload

> **Auth:** Pass `X-Admin-Key` header matching the `ADMIN_UPLOAD_SECRET` environment variable.

### Bulk Upload

```
POST /kb-admin/bulk-upload
```

**Swift (Multipart):**

```swift
extension NetworkService {
    func bulkUploadKB(files: [URL], category: String = "general", tags: [String] = [], adminKey: String) async throws -> [String: Any] {
        let boundary = UUID().uuidString
        var request = URLRequest(url: URL(string: "\(APIConfig.baseURL)/kb-admin/bulk-upload")!)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue(adminKey, forHTTPHeaderField: "X-Admin-Key")
        
        var body = Data()
        
        // Add category
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"category\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(category)\r\n".data(using: .utf8)!)
        
        // Add tags
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"tags\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(tags.joined(separator: ","))\r\n".data(using: .utf8)!)
        
        // Add files
        for fileURL in files {
            let fileData = try Data(contentsOf: fileURL)
            let fileName = fileURL.lastPathComponent
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
            body.append(fileData)
            body.append("\r\n".data(using: .utf8)!)
        }
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body
        
        let (data, _) = try await session.data(for: request)
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }
}
```

### List KB Documents

```
GET /kb-admin/list?category=research&limit=100&offset=0
```

### Delete KB Document

```
DELETE /kb-admin/documents/{document_id}
```

### Upload Pre-Parsed

```
POST /kb-admin/upload-preparsed
```

**Request Body:**
```json
{
  "documents": [
    {
      "filename": "report.pdf",
      "file_type": "application/pdf",
      "file_size": 245678,
      "extracted_text": "Full text content...",
      "content_hash": "sha256-hash-of-original-file",
      "category": "research",
      "tags": ["2024", "earnings"]
    }
  ]
}
```

### KB Stats

```
GET /kb-admin/stats
```

---

## 20. Health & Diagnostics

### Health Check

```
GET /health/
```

**Swift:**

```swift
extension NetworkService {
    func healthCheck() async throws -> [String: Any] {
        let data: [String: AnyCodable] = try await self.request("/health/", requiresAuth: false)
        return data.mapValues { $0.value }
    }
}
```

### Database Health

```
GET /health/db
```

### Config Check

```
GET /health/config
```

### Migration Check

```
GET /health/migrations
```

### Root Endpoint

```
GET /
```

**Response:**
```json
{
  "name": "Analyst by Potomac API",
  "version": "2.0",
  "status": "online",
  "routers_loaded": ["auth", "chat", "ai", "afl", ...],
  "routers_failed": null
}
```

---

## 21. Rate Limiting

The API enforces **120 requests per minute per IP address**. Rate-limited requests receive:

- **HTTP Status:** `429 Too Many Requests`
- **Header:** `Retry-After: 60`
- **Body:** `{"detail": "Rate limit exceeded. Try again in a minute."}`

**Swift Handling:**

```swift
enum APIRateLimitError: Error {
    case limited(retryAfter: Int)
}

extension NetworkService {
    func requestWithRetry<T: Decodable>(
        _ endpoint: String,
        method: String = "GET",
        body: Encodable? = nil,
        maxRetries: Int = 3
    ) async throws -> T {
        var retries = 0
        
        while true {
            do {
                return try await self.request(endpoint, method: method, body: body)
            } catch let error as NSError where error.code == 429 {
                retries += 1
                if retries > maxRetries {
                    throw error
                }
                let delay = Double(error.userInfo["Retry-After"] as? Int ?? 60)
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            }
        }
    }
}
```

---

## 22. Error Handling

All errors follow this format:

```json
{
  "detail": "Human-readable error message"
}
```

**Swift Error Model:**

```swift
enum PotomacAPIError: LocalizedError {
    case unauthorized
    case forbidden
    case notFound(resource: String)
    case rateLimited(retryAfter: Int)
    case serverError(message: String)
    case validationError(message: String)
    case networkError(Error)
    
    var errorDescription: String? {
        switch self {
        case .unauthorized: return "Authentication required. Please log in."
        case .forbidden: return "You don't have permission to perform this action."
        case .notFound(let resource): return "\(resource) not found."
        case .rateLimited(let seconds): return "Rate limited. Try again in \(seconds) seconds."
        case .serverError(let message): return "Server error: \(message)"
        case .validationError(let message): return "Validation error: \(message)"
        case .networkError(let error): return "Network error: \(error.localizedDescription)"
        }
    }
}

// Enhanced request with proper error mapping
extension NetworkService {
    func requestWithMappedErrors<T: Decodable>(
        _ endpoint: String,
        method: String = "GET",
        body: Encodable? = nil,
        requiresAuth: Bool = true
    ) async throws -> T {
        do {
            return try await self.request(endpoint, method: method, body: body, requiresAuth: requiresAuth)
        } catch let error as NSError {
            switch error.code {
            case 401: throw PotomacAPIError.unauthorized
            case 403: throw PotomacAPIError.forbidden
            case 404: throw PotomacAPIError.notFound(resource: endpoint)
            case 429:
                let retryAfter = error.userInfo["Retry-After"] as? Int ?? 60
                throw PotomacAPIError.rateLimited(retryAfter: retryAfter)
            case 500...599: throw PotomacAPIError.serverError(message: error.localizedDescription)
            case 400: throw PotomacAPIError.validationError(message: error.localizedDescription)
            default: throw PotomacAPIError.networkError(error)
            }
        }
    }
}
```

---

## 23. Complete Swift Networking Layer

Here's a complete, production-ready Swift networking layer combining everything above:

```swift
import Foundation
import Combine

// MARK: - Configuration
struct APIConfig {
    static let baseURL = "https://developer-potomaac.up.railway.app"
}

// MARK: - Network Manager
@MainActor
class NetworkManager: ObservableObject {
    static let shared = NetworkManager()
    
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()
    
    @Published var isAuthenticated = false
    @Published var currentUser: UserResponse?
    
    var authToken: String? {
        didSet {
            if let token = authToken {
                UserDefaults.standard.set(token, forKey: "auth_token")
                isAuthenticated = true
            } else {
                UserDefaults.standard.removeObject(forKey: "auth_token")
                isAuthenticated = false
            }
        }
    }
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 300
        session = URLSession(configuration: config)
        
        authToken = UserDefaults.standard.string(forKey: "auth_token")
        isAuthenticated = authToken != nil
    }
    
    // MARK: - Generic Request
    func request<T: Decodable>(
        _ endpoint: String,
        method: String = "GET",
        body: Encodable? = nil,
        requiresAuth: Bool = true,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        guard var components = URLComponents(string: "\(APIConfig.baseURL)\(endpoint)") else {
            throw URLError(.badURL)
        }
        components.queryItems = queryItems
        
        guard let url = components.url else { throw URLError(.badURL) }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if requiresAuth, let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        if let body = body {
            request.httpBody = try encoder.encode(body)
        }
        
        let (data, response) = try await session.data(for: request)
        
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        guard (200...299).contains(http.statusCode) else {
            if let apiError = try? decoder.decode(APIError.self, from: data) {
                throw NSError(domain: "API", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: apiError.detail])
            }
            throw URLError(.badServerResponse)
        }
        
        return try decoder.decode(T.self, from: data)
    }
    
    // MARK: - Streaming
    func stream(
        _ endpoint: String,
        method: String = "POST",
        body: Encodable? = nil
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    guard let url = URL(string: "\(APIConfig.baseURL)\(endpoint)") else {
                        throw URLError(.badURL)
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = method
                    request.setValue("text/plain", forHTTPHeaderField: "Accept")
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    if let token = self.authToken {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    if let body = body {
                        request.httpBody = try self.encoder.encode(body)
                    }
                    
                    let (bytes, _) = try await self.session.bytes(for: request)
                    for try await line in bytes.lines {
                        continuation.yield(line)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - File Upload
    func upload(
        _ endpoint: String,
        fileURL: URL,
        fileName: String,
        mimeType: String,
        fields: [String: String] = [:]
    ) async throws -> Data {
        let boundary = UUID().uuidString
        var request = URLRequest(url: URL(string: "\(APIConfig.baseURL)\(endpoint)")!)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        var body = Data()
        for (key, value) in fields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        
        let fileData = try Data(contentsOf: fileURL)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        let (data, _) = try await session.data(for: request)
        return data
    }
}
```

---

## Quick Reference: All Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | No | Register new user |
| POST | `/auth/login` | No | Login |
| POST | `/auth/logout` | Yes | Logout |
| GET | `/auth/me` | Yes | Current user |
| PUT | `/auth/me` | Yes | Update profile |
| PUT | `/auth/api-keys` | Yes | Update API keys |
| GET | `/auth/api-keys` | Yes | API keys status |
| POST | `/auth/forgot-password` | No | Request password reset |
| POST | `/auth/reset-password` | Yes | Reset password |
| PUT | `/auth/change-password` | Yes | Change password |
| POST | `/auth/refresh-token` | Yes | Refresh token |
| GET | `/auth/admin/users` | Yes | List users (admin) |
| POST | `/auth/admin/users/{id}/make-admin` | Yes | Make admin |
| POST | `/auth/admin/users/{id}/revoke-admin` | Yes | Revoke admin |
| POST | `/auth/admin/users/{id}/deactivate` | Yes | Deactivate user |
| POST | `/auth/admin/users/{id}/activate` | Yes | Activate user |
| GET | `/chat/conversations` | Yes | List conversations |
| POST | `/chat/conversations` | Yes | Create conversation |
| GET | `/chat/conversations/{id}/messages` | Yes | Get messages |
| PATCH | `/chat/conversations/{id}` | Yes | Rename conversation |
| DELETE | `/chat/conversations/{id}` | Yes | Delete conversation |
| POST | `/chat/agent` | Yes | Chat agent (streaming) |
| GET | `/chat/models` | Yes | List models |
| POST | `/chat/tts` | Yes | Text-to-speech |
| GET | `/chat/tts/voices` | No | List TTS voices |
| GET | `/ai/status` | No | AI status |
| GET | `/ai/skills` | Yes | List invokable skills |
| GET | `/ai/skills/{slug}` | Yes | Skill detail |
| POST | `/ai/skills/{slug}` | Yes | Invoke skill (streaming) |
| POST | `/afl/generate` | Yes | Generate AFL |
| POST | `/afl/optimize` | Yes | Optimize AFL |
| POST | `/afl/debug` | Yes | Debug AFL |
| POST | `/afl/explain` | Yes | Explain AFL |
| POST | `/afl/validate` | No | Validate AFL |
| GET | `/afl/codes` | Yes | List AFL codes |
| GET | `/afl/codes/{id}` | Yes | Get AFL code |
| DELETE | `/afl/codes/{id}` | Yes | Delete AFL code |
| POST | `/afl/history` | Yes | Save AFL history |
| GET | `/afl/history` | Yes | Get AFL history |
| DELETE | `/afl/history/{id}` | Yes | Delete AFL history |
| POST | `/afl/upload` | Yes | Upload AFL file |
| GET | `/afl/files` | Yes | List AFL files |
| GET | `/afl/files/{id}` | Yes | Get AFL file |
| DELETE | `/afl/files/{id}` | Yes | Delete AFL file |
| POST | `/afl/settings/presets` | Yes | Save preset |
| GET | `/afl/settings/presets` | Yes | List presets |
| GET | `/afl/settings/presets/{id}` | Yes | Get preset |
| PUT | `/afl/settings/presets/{id}` | Yes | Update preset |
| DELETE | `/afl/settings/presets/{id}` | Yes | Delete preset |
| POST | `/afl/settings/presets/{id}/set-default` | Yes | Set default preset |
| POST | `/brain/upload` | Yes | Upload document |
| POST | `/brain/upload-batch` | Yes | Batch upload |
| POST | `/brain/upload-text` | Yes | Upload text |
| POST | `/brain/search` | Yes | Search KB |
| GET | `/brain/documents` | Yes | List documents |
| GET | `/brain/documents/{id}` | Yes | Get document |
| GET | `/brain/documents/{id}/content` | Yes | Get document content |
| GET | `/brain/documents/{id}/download` | Yes | Download document |
| DELETE | `/brain/documents/{id}` | Yes | Delete document |
| GET | `/brain/stats` | Yes | KB stats |
| POST | `/upload/direct` | Yes | Direct upload |
| POST | `/upload/conversations/{id}` | Yes | Upload to conversation |
| GET | `/upload/files` | Yes | List files |
| GET | `/upload/files/{id}` | Yes | Get file info |
| GET | `/upload/files/{id}/download` | Yes | Download file |
| DELETE | `/upload/files/{id}` | Yes | Delete file |
| POST | `/upload/files/{id}/extract` | Yes | Extract text |
| GET | `/upload/conversations/{id}/files` | Yes | Conversation files |
| POST | `/upload/files/{id}/link/{conv_id}` | Yes | Link file |
| GET | `/upload/info` | No | Storage info |
| GET | `/files/{id}/download` | Yes | Download generated file |
| GET | `/files/{id}/info` | Yes | File info |
| GET | `/files/generated` | Yes | List generated files |
| POST | `/backtest/upload` | Yes | Upload backtest |
| GET | `/backtest/history` | Yes | List backtests |
| GET | `/backtest/{id}` | Yes | Get backtest |
| GET | `/backtest/strategy/{id}` | Yes | Strategy backtests |
| GET | `/researcher/company/{symbol}` | Yes | Company research |
| GET | `/researcher/company/{symbol}/stream` | Yes | Research (streaming) |
| GET | `/researcher/news/{symbol}` | Yes | Company news |
| POST | `/researcher/strategy-analysis` | Yes | Strategy analysis |
| POST | `/researcher/comparison` | Yes | Peer comparison |
| GET | `/researcher/macro-context` | Yes | Macro context |
| GET | `/researcher/sec-filings/{symbol}` | Yes | SEC filings |
| POST | `/researcher/generate-report` | Yes | Generate report |
| GET | `/researcher/reports/{id}/export` | Yes | Export report |
| GET | `/researcher/search` | Yes | Search research |
| GET | `/researcher/trending` | Yes | Trending research |
| GET | `/researcher/health` | No | Researcher health |
| GET | `/skills` | Yes | List skills |
| GET | `/skills/categories` | Yes | Skill categories |
| GET | `/skills/jobs` | Yes | Skill jobs |
| GET | `/skills/{slug}` | Yes | Skill detail |
| GET | `/yfinance/{ticker}` | Yes | Comprehensive data |
| GET | `/yfinance/{ticker}/summary` | Yes | Quick summary |
| GET | `/yfinance/{ticker}/history` | Yes | Price history |
| GET | `/edgar/security/{identifier}` | Yes | Security ID lookup |
| GET | `/edgar/search` | Yes | Search companies |
| GET | `/edgar/company/{cik}` | Yes | Company info |
| GET | `/edgar/company/{cik}/filings` | Yes | Company filings |
| GET | `/edgar/company/{cik}/filings/{accn}` | Yes | Filing documents |
| GET | `/edgar/company/{cik}/financials` | Yes | Key financials |
| GET | `/edgar/company/{cik}/concept` | Yes | XBRL concept |
| GET | `/edgar/ticker/{ticker}/filings` | Yes | Ticker filings |
| GET | `/edgar/ticker/{ticker}/annual` | Yes | Annual filings |
| GET | `/edgar/ticker/{ticker}/quarterly` | Yes | Quarterly filings |
| GET | `/edgar/ticker/{ticker}/events` | Yes | Material events |
| GET | `/edgar/ticker/{ticker}/insider` | Yes | Insider transactions |
| GET | `/edgar/ticker/{ticker}/proxy` | Yes | Proxy statements |
| GET | `/edgar/ticker/{ticker}/financials` | Yes | Ticker financials |
| POST | `/edgar/search/fulltext` | Yes | Full-text search |
| GET | `/edgar/tickers` | Yes | All tickers |
| POST | `/tasks` | Yes | Submit task |
| GET | `/tasks` | Yes | List tasks |
| GET | `/tasks/{id}` | Yes | Get task |
| POST | `/tasks/{id}/cancel` | Yes | Cancel task |
| DELETE | `/tasks/{id}` | Yes | Dismiss task |
| DELETE | `/tasks` | Yes | Clear completed |
| POST | `/consensus/validate` | Yes | Run consensus |
| GET | `/consensus/models` | Yes | Consensus models |
| POST | `/train/feedback` | Yes | Submit feedback |
| GET | `/train/feedback/my` | Yes | My feedback |
| GET | `/train/feedback/{id}` | Yes | Feedback detail |
| POST | `/train/test` | Yes | Test training |
| GET | `/train/effectiveness` | Yes | Training effectiveness |
| POST | `/train/suggest` | Yes | Suggest training |
| GET | `/train/suggestions/my` | Yes | My suggestions |
| POST | `/train/quick-learn` | Yes | Quick learn |
| GET | `/train/analytics/learning-curve` | Yes | Learning curve |
| GET | `/train/analytics/popular-patterns` | Yes | Popular patterns |
| GET | `/train/knowledge/search` | Yes | Search knowledge |
| GET | `/train/knowledge/categories` | Yes | Knowledge categories |
| GET | `/train/knowledge/types` | Yes | Knowledge types |
| GET | `/train/stats` | Yes | Training stats |
| GET | `/admin/status` | Yes | Admin status |
| POST | `/admin/make-admin/{id}` | Yes | Make admin |
| POST | `/admin/revoke-admin/{id}` | Yes | Revoke admin |
| POST | `/admin/train` | Yes | Add training |
| POST | `/admin/train/quick` | Yes | Quick train |
| POST | `/admin/train/correction` | Yes | Add correction |
| POST | `/admin/train/batch` | Yes | Batch import |
| GET | `/admin/training` | Yes | List training |
| GET | `/admin/training/{id}` | Yes | Get training |
| PUT | `/admin/training/{id}` | Yes | Update training |
| DELETE | `/admin/training/{id}` | Yes | Delete training |
| POST | `/admin/training/{id}/toggle` | Yes | Toggle training |
| GET | `/admin/training/stats/overview` | Yes | Training stats |
| GET | `/admin/training/export/all` | Yes | Export training |
| GET | `/admin/training/context/preview` | Yes | Preview context |
| GET | `/admin/users` | Yes | List users |
| GET | `/admin/users/{id}` | Yes | Get user |
| PUT | `/admin/users/{id}` | Yes | Update user |
| DELETE | `/admin/users/{id}` | Yes | Delete user |
| POST | `/admin/users/{id}/restore` | Yes | Restore user |
| GET | `/admin/config` | Yes | Get config |
| PUT | `/admin/config` | Yes | Update config |
| POST | `/admin/config/add-admin-email` | Yes | Add admin email |
| GET | `/admin/feedback` | Yes | List feedback |
| GET | `/admin/feedback/{id}` | Yes | Get feedback |
| POST | `/admin/feedback/{id}/review` | Yes | Review feedback |
| GET | `/admin/suggestions` | Yes | List suggestions |
| GET | `/admin/suggestions/{id}` | Yes | Get suggestion |
| POST | `/admin/suggestions/{id}/review` | Yes | Review suggestion |
| POST | `/admin/suggestions/{id}/approve` | Yes | Approve suggestion |
| POST | `/admin/suggestions/{id}/reject` | Yes | Reject suggestion |
| GET | `/admin/analytics/overview` | Yes | Analytics overview |
| GET | `/admin/analytics/trends` | Yes | Analytics trends |
| GET | `/admin/analytics/engagement` | Yes | Engagement metrics |
| GET | `/admin/audit-logs` | Yes | Audit logs |
| GET | `/admin/health/system` | Yes | System health |
| POST | `/admin/maintenance/toggle` | Yes | Toggle maintenance |
| GET | `/admin/export/users` | Yes | Export users |
| GET | `/admin/export/feedback` | Yes | Export feedback |
| GET | `/admin/export/training` | Yes | Export training |
| POST | `/api/generate-presentation` | Yes | Generate presentation |
| POST | `/api/generate-presentation/test` | No | Test presentation |
| POST | `/kb-admin/bulk-upload` | No* | Bulk upload |
| GET | `/kb-admin/list` | No* | List KB docs |
| DELETE | `/kb-admin/documents/{id}` | No* | Delete KB doc |
| POST | `/kb-admin/upload-preparsed` | No* | Upload pre-parsed |
| GET | `/kb-admin/stats` | No* | KB stats |
| GET | `/health/` | No | Health check |
| GET | `/health/db` | No | Database health |
| GET | `/health/config` | No | Config check |
| GET | `/health/migrations` | No | Migration check |
| GET | `/files/{id}/preview` | Yes | File preview |
| GET | `/` | No | Root info |

> \* KB Admin endpoints use `X-Admin-Key` header instead of Bearer JWT.

---

**Last Updated:** March 2026
**API Version:** 2.0
**Base URL:** `https://developer-potomaac.up.railway.app/`