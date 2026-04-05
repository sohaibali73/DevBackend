# WinUI 3 Integration Guide
Analyst by Potomac API | Windows App SDK

---

## Prerequisites
- Windows 10 1809+ / Windows 11
- Visual Studio 2022 with Windows App SDK workload
- Windows App SDK 1.4+
- .NET 7+ / .NET 8
- NuGet packages:
  - `Microsoft.Windows.SDK.BuildTools`
  - `Microsoft.WindowsAppSDK`
  - `System.Net.Http.Json`
  - `System.Text.Json`

---

## Step 1: HttpClient Configuration
Add this to your `App.xaml.cs` for a reusable HttpClient instance:

```csharp
using System.Net.Http;
using System.Net.Http.Headers;

public static class ApiClient
{
    private static HttpClient _httpClient;
    
    public static HttpClient Instance
    {
        get
        {
            if (_httpClient == null)
            {
                _httpClient = new HttpClient
                {
                    BaseAddress = new Uri("https://developer-potomaac.up.railway.app/"),
                    Timeout = TimeSpan.FromSeconds(120)
                };
                _httpClient.DefaultRequestHeaders.Accept.Add(
                    new MediaTypeWithQualityHeaderValue("application/json"));
            }
            return _httpClient;
        }
    }
    
    public static void SetAuthToken(string token)
    {
        Instance.DefaultRequestHeaders.Authorization = 
            new AuthenticationHeaderValue("Bearer", token);
    }
    
    public static void ClearAuthToken()
    {
        Instance.DefaultRequestHeaders.Authorization = null;
    }
}
```

---

## Step 2: Authentication Implementation

### Login Method
```csharp
public class AuthService
{
    public async Task<string> LoginAsync(string email, string password)
    {
        var loginData = new
        {
            email = email,
            password = password
        };

        var response = await ApiClient.Instance.PostAsJsonAsync("auth/login", loginData);
        
        if (response.IsSuccessStatusCode)
        {
            var result = await response.Content.ReadFromJsonAsync<LoginResponse>();
            ApiClient.SetAuthToken(result.AccessToken);
            return result.AccessToken;
        }
        
        throw new Exception($"Login failed: {response.StatusCode}");
    }
}

public class LoginResponse
{
    [JsonPropertyName("access_token")]
    public string AccessToken { get; set; }
    
    [JsonPropertyName("token_type")]
    public string TokenType { get; set; }
    
    [JsonPropertyName("expires_in")]
    public int ExpiresIn { get; set; }
}
```

---

## Step 3: API Endpoint Implementations

### Chat Completion Example
```csharp
public async Task<string> SendChatMessage(string message)
{
    var request = new
    {
        message = message,
        stream = false
    };

    var response = await ApiClient.Instance.PostAsJsonAsync("ai/chat", request);
    response.EnsureSuccessStatusCode();
    
    return await response.Content.ReadAsStringAsync();
}
```

### AFL Code Generation
```csharp
public async Task<string> GenerateAfl(string indicatorDescription)
{
    var request = new
    {
        description = indicatorDescription,
        type = "indicator"
    };

    var response = await ApiClient.Instance.PostAsJsonAsync("afl/generate", request);
    return await response.Content.ReadAsStringAsync();
}
```

### File Upload
```csharp
public async Task<string> UploadFile(StorageFile file)
{
    using var content = new MultipartFormDataContent();
    using var stream = await file.OpenStreamForReadAsync();
    
    content.Add(new StreamContent(stream), "file", file.Name);
    
    var response = await ApiClient.Instance.PostAsync("upload/file", content);
    return await response.Content.ReadAsStringAsync();
}
```

---

## Step 4: Streaming Support (SSE)
For real-time AI streaming:
```csharp
public async Task StreamChat(string prompt, Action<string> onChunkReceived)
{
    var request = new
    {
        prompt = prompt,
        stream = true
    };

    using var response = await ApiClient.Instance.PostAsJsonAsync("ai/stream", request, 
        HttpCompletionOption.ResponseHeadersRead);
    
    response.EnsureSuccessStatusCode();
    
    using var stream = await response.Content.ReadAsStreamAsync();
    using var reader = new StreamReader(stream);
    
    string line;
    while ((line = await reader.ReadLineAsync()) != null)
    {
        if (line.StartsWith("data: ") && line != "data: [DONE]")
        {
            var data = line.Substring(6);
            onChunkReceived?.Invoke(data);
        }
    }
}
```

---

## Step 5: Error Handling
```csharp
public static class ApiErrorHandler
{
    public static async Task HandleApiError(HttpResponseMessage response)
    {
        var errorContent = await response.Content.ReadFromJsonAsync<ApiError>();
        
        switch (response.StatusCode)
        {
            case HttpStatusCode.Unauthorized:
                // Clear token and redirect to login
                ApiClient.ClearAuthToken();
                break;
                
            case HttpStatusCode.TooManyRequests:
                // Rate limit hit, show retry dialog
                var retryAfter = response.Headers.RetryAfter?.Delta?.TotalSeconds ?? 60;
                break;
        }
    }
}

public class ApiError
{
    [JsonPropertyName("detail")]
    public string Detail { get; set; }
    
    [JsonPropertyName("type")]
    public string Type { get; set; }
}
```

---

## Best Practices for WinUI 3
1.  Always use `async/await` pattern
2.  Never call API on UI thread directly
3.  Use `DispatcherQueue` to update UI from API callbacks
4.  Implement cancellation tokens for long-running requests
5.  Handle network connectivity changes
6.  Add retry policy with `Polly` for transient errors
7.  Cache auth token securely using `Windows.Security.Credentials.PasswordVault`

---

## Example WinUI 3 Page
```xml
<Page
    x:Class="PotomacClient.Views.ChatPage"
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    
    <StackPanel Padding="24">
        <TextBox x:Name="PromptBox" PlaceholderText="Enter your message..." />
        <Button Click="OnSendClick" Content="Send" Margin="0 12 0 0" />
        <TextBox x:Name="ResultBox" AcceptsReturn="True" Height="400" Margin="0 12 0 0" />
    </StackPanel>
</Page>
```

```csharp
private async void OnSendClick(object sender, RoutedEventArgs e)
{
    try
    {
        var result = await _chatService.SendChatMessage(PromptBox.Text);
        ResultBox.Text = result;
    }
    catch (Exception ex)
    {
        ContentDialog errorDialog = new ContentDialog
        {
            Title = "Error",
            Content = ex.Message,
            CloseButtonText = "OK"
        };
        await errorDialog.ShowAsync();
    }
}
```

---

## Supported Endpoints in WinUI 3
All API endpoints are fully compatible with WinUI 3. Use standard `HttpClient` for all requests. Streaming endpoints work with SSE protocol as demonstrated.

---

## Troubleshooting
- **CORS Issues**: API allows all origins, no issues with WinUI 3
- **Timeout**: Increase HttpClient timeout for long operations
- **SSL**: Modern Windows versions handle TLS 1.2+ automatically
- **Proxy**: HttpClient uses system proxy settings by default