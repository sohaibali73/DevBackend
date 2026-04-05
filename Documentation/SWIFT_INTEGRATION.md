# Swift Integration Guide
Analyst by Potomac API | iOS / macOS / tvOS / watchOS

---

## Requirements
- iOS 15.0+ / macOS 12.0+
- Swift 5.7+
- Xcode 14+
- Dependencies:
  - Foundation (built-in)
  - `URLSession` (built-in)
  - Optional: `Alamofire` 5.0+

---

## Step 1: API Client Configuration

```swift
import Foundation

final class PotomacAPIClient {
    static let shared = PotomacAPIClient()
    
    private let baseURL = URL(string: "https://developer-potomaac.up.railway.app/")!
    private let session: URLSession
    
    var authToken: String? {
        didSet {
            updateAuthorizationHeader()
        }
    }
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)
    }
    
    private func updateAuthorizationHeader() {
        session.configuration.httpAdditionalHeaders?["Authorization"] = 
            authToken.map { "Bearer \($0)" }
    }
}
```

---

## Step 2: Authentication

```swift
extension PotomacAPIClient {
    func login(email: String, password: String) async throws -> AuthResponse {
        var request = URLRequest(url: baseURL.appendingPathComponent("auth/login"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["email": email, "password": password]
        request.httpBody = try JSONEncoder().encode(body)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        
        let authResponse = try JSONDecoder().decode(AuthResponse.self, from: data)
        self.authToken = authResponse.accessToken
        
        // Save token securely to Keychain
        try KeychainHelper.save(token: authResponse.accessToken)
        
        return authResponse
    }
}

struct AuthResponse: Codable {
    let accessToken: String
    let tokenType: String
    let expiresIn: Int
    
    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}
```

---

## Step 3: Generic Request Method

```swift
extension PotomacAPIClient {
    func request<T: Decodable>(
        method: HTTPMethod,
        path: String,
        parameters: [String: Any]? = nil
    ) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let parameters = parameters {
            request.httpBody = try JSONSerialization.data(withJSONObject: parameters)
        }
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        
        switch httpResponse.statusCode {
        case 200...299:
            return try JSONDecoder().decode(T.self, from: data)
        case 401:
            self.authToken = nil
            throw APIError.unauthorized
        case 429:
            let retryAfter = httpResponse.value(forHTTPHeaderField: "Retry-After") ?? "60"
            throw APIError.rateLimitExceeded(retryAfter: Double(retryAfter) ?? 60)
        default:
            let error = try JSONDecoder().decode(APIErrorResponse.self, from: data)
            throw APIError.serverError(message: error.detail)
        }
    }
}
```

---

## Step 4: Endpoint Examples

### Chat Completion
```swift
extension PotomacAPIClient {
    func sendChatMessage(_ message: String) async throws -> ChatResponse {
        try await request(
            method: .post,
            path: "ai/chat",
            parameters: ["message": message, "stream": false]
        )
    }
}
```

### AFL Generation
```swift
func generateAFL(description: String, type: String = "indicator") async throws -> AFLResponse {
    try await request(
        method: .post,
        path: "afl/generate",
        parameters: ["description": description, "type": type]
    )
}
```

### File Upload
```swift
func uploadFile(data: Data, fileName: String, mimeType: String) async throws -> UploadResponse {
    var request = URLRequest(url: baseURL.appendingPathComponent("upload/file"))
    request.httpMethod = "POST"
    
    let boundary = UUID().uuidString
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
    
    var body = Data()
    body.append("--\(boundary)\r\n".data(using: .utf8)!)
    body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
    body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
    body.append(data)
    body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
    
    request.httpBody = body
    
    let (responseData, _) = try await session.data(for: request)
    return try JSONDecoder().decode(UploadResponse.self, from: responseData)
}
```

---

## Step 5: Streaming Support
```swift
func streamChat(prompt: String, onChunk: @escaping (String) -> Void) async throws {
    var request = URLRequest(url: baseURL.appendingPathComponent("ai/stream"))
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    
    let body = ["prompt": prompt, "stream": true]
    request.httpBody = try JSONEncoder().encode(body)
    
    let (bytes, _) = try await session.bytes(for: request)
    
    for try await line in bytes.lines {
        if line.hasPrefix("data: "), line != "data: [DONE]" {
            let chunk = String(line.dropFirst(6))
            onChunk(chunk)
        }
    }
}
```

---

## Step 6: Error Handling

```swift
enum APIError: Error {
    case invalidResponse
    case unauthorized
    case rateLimitExceeded(retryAfter: Double)
    case serverError(message: String)
    case networkError(Error)
}

struct APIErrorResponse: Decodable {
    let detail: String
    let type: String?
}
```

---

## Best Practices
1.  Use Swift Concurrency (`async/await`) for all API calls
2.  Store auth tokens in Keychain, not UserDefaults
3.  Implement automatic token refresh
4.  Add retry logic with exponential backoff
5.  Cancel requests when view controllers are dismissed
6.  Use `@MainActor` for UI updates from API responses
7.  Monitor network reachability with `NWPathMonitor`

---

## SwiftUI Example Usage

```swift
struct ChatView: View {
    @State private var message = ""
    @State private var response = ""
    @State private var isLoading = false
    
    var body: some View {
        VStack {
            TextField("Enter message", text: $message)
                .textFieldStyle(.roundedBorder)
            
            Button("Send") {
                Task {
                    isLoading = true
                    do {
                        let result = try await PotomacAPIClient.shared.sendChatMessage(message)
                        response = result.content
                    } catch {
                        print("Error: \(error)")
                    }
                    isLoading = false
                }
            }
            .disabled(isLoading)
            
            Text(response)
                .padding()
        }
        .padding()
    }
}
```

---

## Supported Platforms
✅ iOS 15.0+
✅ macOS 12.0+
✅ tvOS 15.0+
✅ watchOS 8.0+
✅ visionOS 1.0+

All API endpoints are fully compatible with Swift and Apple platforms.