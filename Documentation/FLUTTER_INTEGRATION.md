# Flutter Integration Guide
Analyst by Potomac API | Cross Platform Mobile / Desktop / Web

---

## Requirements
- Flutter 3.10+
- Dart 3.0+
- Dependencies:
  - `http: ^1.1.0`
  - `dio: ^5.3.0` (optional alternative)
  - `flutter_secure_storage: ^9.0.0`
  - `json_annotation: ^4.8.1`

---

## Step 1: Add Dependencies
Add to your `pubspec.yaml`:

```yaml
dependencies:
  flutter:
    sdk: flutter
  http: ^1.1.0
  flutter_secure_storage: ^9.0.0
  json_annotation: ^4.8.1

dev_dependencies:
  build_runner: ^2.4.6
  json_serializable: ^6.7.1
```

---

## Step 2: API Client Setup

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

class PotomacApiClient {
  static final PotomacApiClient _instance = PotomacApiClient._internal();
  factory PotomacApiClient() => _instance;
  
  static const String baseUrl = 'https://developer-potomaac.up.railway.app/';
  String? _authToken;
  
  PotomacApiClient._internal();
  
  set authToken(String? token) {
    _authToken = token;
  }
  
  Map<String, String> get headers {
    final headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    
    if (_authToken != null) {
      headers['Authorization'] = 'Bearer $_authToken';
    }
    
    return headers;
  }
}
```

---

## Step 3: Authentication Service

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  final _storage = const FlutterSecureStorage();
  final _api = PotomacApiClient();
  
  Future<String?> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('${PotomacApiClient.baseUrl}auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': email,
        'password': password,
      }),
    );
    
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final token = data['access_token'];
      
      _api.authToken = token;
      await _storage.write(key: 'auth_token', value: token);
      
      return token;
    }
    
    throw ApiException.fromResponse(response);
  }
  
  Future<void> logout() async {
    _api.authToken = null;
    await _storage.delete(key: 'auth_token');
  }
  
  Future<bool> isLoggedIn() async {
    final token = await _storage.read(key: 'auth_token');
    if (token != null) {
      _api.authToken = token;
      return true;
    }
    return false;
  }
}
```

---

## Step 4: Generic Request Method

```dart
Future<T> apiRequest<T>({
  required String method,
  required String path,
  Map<String, dynamic>? body,
  required T Function(Map<String, dynamic>) fromJson,
}) async {
  final url = Uri.parse('${PotomacApiClient.baseUrl}$path');
  final headers = PotomacApiClient().headers;
  
  http.Response response;
  
  switch (method.toUpperCase()) {
    case 'POST':
      response = await http.post(url, headers: headers, body: jsonEncode(body));
      break;
    case 'GET':
      response = await http.get(url, headers: headers);
      break;
    case 'DELETE':
      response = await http.delete(url, headers: headers);
      break;
    default:
      throw UnsupportedError('Method $method not supported');
  }
  
  if (response.statusCode >= 200 && response.statusCode < 300) {
    return fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 401) {
    await AuthService().logout();
    throw UnauthorizedException();
  } else if (response.statusCode == 429) {
    final retryAfter = int.tryParse(response.headers['retry-after'] ?? '60') ?? 60;
    throw RateLimitException(retryAfter);
  } else {
    throw ApiException.fromResponse(response);
  }
}
```

---

## Step 5: Model Classes with JSON Serialization

```dart
import 'package:json_annotation/json_annotation.dart';

part 'api_models.g.dart';

@JsonSerializable()
class AuthResponse {
  @JsonKey(name: 'access_token')
  final String accessToken;
  
  @JsonKey(name: 'token_type')
  final String tokenType;
  
  @JsonKey(name: 'expires_in')
  final int expiresIn;
  
  AuthResponse({
    required this.accessToken,
    required this.tokenType,
    required this.expiresIn,
  });
  
  factory AuthResponse.fromJson(Map<String, dynamic> json) => _$AuthResponseFromJson(json);
  Map<String, dynamic> toJson() => _$AuthResponseToJson(this);
}

@JsonSerializable()
class ChatResponse {
  final String content;
  final String model;
  
  ChatResponse({required this.content, required this.model});
  
  factory ChatResponse.fromJson(Map<String, dynamic> json) => _$ChatResponseFromJson(json);
}
```

---

## Step 6: API Endpoint Implementations

```dart
class ChatService {
  Future<ChatResponse> sendMessage(String message) async {
    return apiRequest(
      method: 'POST',
      path: 'ai/chat',
      body: {'message': message, 'stream': false},
      fromJson: ChatResponse.fromJson,
    );
  }
}

class AflService {
  Future<AflResponse> generateAfl(String description) async {
    return apiRequest(
      method: 'POST',
      path: 'afl/generate',
      body: {'description': description, 'type': 'indicator'},
      fromJson: AflResponse.fromJson,
    );
  }
}

class FileService {
  Future<UploadResponse> uploadFile(File file) async {
    var request = http.MultipartRequest(
      'POST',
      Uri.parse('${PotomacApiClient.baseUrl}upload/file'),
    );
    
    request.headers.addAll(PotomacApiClient().headers);
    request.files.add(await http.MultipartFile.fromPath('file', file.path));
    
    final response = await request.send();
    
    if (response.statusCode == 200) {
      final responseData = await response.stream.bytesToString();
      return UploadResponse.fromJson(jsonDecode(responseData));
    }
    
    throw Exception('Upload failed');
  }
}
```

---

## Step 7: Streaming Support

```dart
Stream<String> streamChat(String prompt) async* {
  final request = http.Request(
    'POST',
    Uri.parse('${PotomacApiClient.baseUrl}ai/stream'),
  );
  
  request.headers.addAll(PotomacApiClient().headers);
  request.body = jsonEncode({'prompt': prompt, 'stream': true});
  
  final response = await request.send();
  
  if (response.statusCode == 200) {
    await for (final chunk in response.stream.transform(utf8.decoder).transform(const LineSplitter())) {
      if (chunk.startsWith('data: ') && chunk != 'data: [DONE]') {
        yield chunk.substring(6);
      }
    }
  }
}
```

---

## Step 8: Error Handling

```dart
class ApiException implements Exception {
  final String message;
  final int statusCode;
  
  ApiException(this.message, this.statusCode);
  
  factory ApiException.fromResponse(http.Response response) {
    final data = jsonDecode(response.body);
    return ApiException(data['detail'] ?? 'Unknown error', response.statusCode);
  }
  
  @override
  String toString() => 'API Error $statusCode: $message';
}

class UnauthorizedException extends ApiException {
  UnauthorizedException() : super('Unauthorized', 401);
}

class RateLimitException extends ApiException {
  final int retryAfter;
  RateLimitException(this.retryAfter) : super('Rate limit exceeded', 429);
}
```

---

## Step 9: Flutter Example Usage

```dart
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _controller = TextEditingController();
  String _response = '';
  bool _isLoading = false;
  
  Future<void> _sendMessage() async {
    setState(() => _isLoading = true);
    
    try {
      final result = await ChatService().sendMessage(_controller.text);
      setState(() => _response = result.content);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString())),
        );
      }
    } finally {
      setState(() => _isLoading = false);
    }
  }
  
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Chat')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            TextField(
              controller: _controller,
              decoration: const InputDecoration(labelText: 'Message'),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _isLoading ? null : _sendMessage,
              child: Text(_isLoading ? 'Loading...' : 'Send'),
            ),
            const SizedBox(height: 24),
            Expanded(child: SingleChildScrollView(child: Text(_response))),
          ],
        ),
      ),
    );
  }
}
```

---

## Best Practices
1.  Use `json_serializable` for type-safe JSON parsing
2.  Store auth tokens securely with `flutter_secure_storage`
3.  Implement `dio` with interceptors for advanced use cases
4.  Use `FutureBuilder` / `StreamBuilder` for async UI
5.  Add retry logic with `dio_retry` or custom implementation
6.  Cancel requests when widgets are disposed
7.  Handle network connectivity with `connectivity_plus`

---

## Supported Platforms
✅ Android
✅ iOS
✅ Web
✅ Windows
✅ macOS
✅ Linux

All API endpoints work across all Flutter supported platforms.