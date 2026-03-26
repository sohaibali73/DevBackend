# Analyst by Potomac — Complete WinUI 3 / C# API Guide

> **Base URL:** `https://developer-potomaac.up.railway.app/`
>
> **API Version:** 2.0
>
> **Framework:** WinUI 3 (Windows App SDK) with C# / .NET 8+
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
23. [MVVM Architecture](#23-mvvm-architecture)
24. [Complete Networking Layer](#24-complete-networking-layer)

---

## 1. Getting Started

### Project Setup

Create a new WinUI 3 project:

```bash
dotnet new winui3 -n AnalystApp -o AnalystApp
```

### NuGet Packages

```xml
<!-- AnalystApp.csproj -->
<ItemGroup>
  <PackageReference Include="Microsoft.WindowsAppSDK" Version="1.5.240311000" />
  <PackageReference Include="CommunityToolkit.Mvvm" Version="8.2.2" />
  <PackageReference Include="CommunityToolkit.WinUI.UI.Controls" Version="7.1.2" />
  <PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />
  <PackageReference Include="Microsoft.Extensions.DependencyInjection" Version="8.0.0" />
  <PackageReference Include="System.Text.Json" Version="8.0.3" />
  <PackageReference Include="Polly" Version="8.3.1" />
  <PackageReference Include="Polly.Extensions.Http" Version="3.0.0" />
  <PackageReference Include="IdentityModel.OidcClient" Version="5.2.1" />
</ItemGroup>
```

### Configuration

```csharp
// Services/ApiConfig.cs
namespace AnalystApp.Services;

public static class ApiConfig
{
    public const string BaseUrl = "https://developer-potomaac.up.railway.app";
    public const string ContentType = "application/json";
    public const int TimeoutSeconds = 60;
    public const int MaxRetries = 3;
}
```

### Data Models

```csharp
// Models/ApiModels.cs
using System.Text.Json.Serialization;

namespace AnalystApp.Models;

public class Token
{
    [JsonPropertyName("access_token")]
    public string AccessToken { get; set; } = string.Empty;

    [JsonPropertyName("token_type")]
    public string TokenType { get; set; } = "bearer";

    [JsonPropertyName("user_id")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;

    [JsonPropertyName("expires_in")]
    public int ExpiresIn { get; set; } = 3600;
}

public class ApiResponse<T>
{
    [JsonPropertyName("detail")]
    public string? Detail { get; set; }
}

public class UserResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("email")]
    public string Email { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("nickname")]
    public string? Nickname { get; set; }

    [JsonPropertyName("is_admin")]
    public bool IsAdmin { get; set; }

    [JsonPropertyName("is_active")]
    public bool IsActive { get; set; }

    [JsonPropertyName("has_api_keys")]
    public bool HasApiKeys { get; set; }

    [JsonPropertyName("created_at")]
    public string? CreatedAt { get; set; }
}

public class Conversation
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("conversation_type")]
    public string? ConversationType { get; set; }

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = string.Empty;

    [JsonPropertyName("updated_at")]
    public string UpdatedAt { get; set; } = string.Empty;

    [JsonPropertyName("is_archived")]
    public bool IsArchived { get; set; }

    [JsonPropertyName("is_pinned")]
    public bool IsPinned { get; set; }

    [JsonPropertyName("model")]
    public string? Model { get; set; }
}

public class ChatMessage
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("conversation_id")]
    public string ConversationId { get; set; } = string.Empty;

    [JsonPropertyName("role")]
    public string Role { get; set; } = string.Empty;

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = string.Empty;

    [JsonPropertyName("metadata")]
    public Dictionary<string, object>? Metadata { get; set; }
}

public class FileInfo
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("original_filename")]
    public string OriginalFilename { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string? ContentType { get; set; }

    [JsonPropertyName("file_size")]
    public int? FileSize { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = string.Empty;
}

public class Skill
{
    [JsonPropertyName("skill_id")]
    public string SkillId { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("slug")]
    public string Slug { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("category")]
    public string Category { get; set; } = string.Empty;

    [JsonPropertyName("max_tokens")]
    public int MaxTokens { get; set; }

    [JsonPropertyName("tags")]
    public List<string> Tags { get; set; } = new();

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; }

    [JsonPropertyName("supports_streaming")]
    public bool SupportsStreaming { get; set; }

    [JsonPropertyName("is_builtin")]
    public bool IsBuiltin { get; set; }
}

public class TaskResponse
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("user_id")]
    public string UserId { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("task_type")]
    public string TaskType { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("progress")]
    public int Progress { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("created_at")]
    public double CreatedAt { get; set; }

    [JsonPropertyName("started_at")]
    public double? StartedAt { get; set; }

    [JsonPropertyName("completed_at")]
    public double? CompletedAt { get; set; }

    [JsonPropertyName("elapsed_seconds")]
    public double ElapsedSeconds { get; set; }
}
```

### Secure Storage

```csharp
// Services/SecureStorage.cs
using Windows.Security.Credentials;

namespace AnalystApp.Services;

public static class SecureStorage
{
    private const string ResourceName = "AnalystApp";

    public static void SaveToken(string token)
    {
        var vault = new PasswordVault();
        // Remove existing
        try
        {
            var existing = vault.Retrieve(ResourceName, "auth_token");
            vault.Remove(existing);
        }
        catch { }

        vault.Add(new PasswordCredential(ResourceName, "auth_token", token));
    }

    public static string? GetToken()
    {
        try
        {
            var vault = new PasswordVault();
            var credential = vault.Retrieve(ResourceName, "auth_token");
            credential.RetrievePassword();
            return credential.Password;
        }
        catch
        {
            return null;
        }
    }

    public static void ClearToken()
    {
        try
        {
            var vault = new PasswordVault();
            var credential = vault.Retrieve(ResourceName, "auth_token");
            vault.Remove(credential);
        }
        catch { }
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

**C# Implementation:**

```csharp
// Services/ApiService.Auth.cs
using System.Net.Http.Json;
using System.Text.Json;

namespace AnalystApp.Services;

public partial class ApiService
{
    public async Task<Token> RegisterAsync(string email, string password, string? name = null)
    {
        var request = new
        {
            email,
            password,
            name
        };

        var response = await _httpClient.PostAsJsonAsync("/auth/register", request);
        response.EnsureSuccessStatusCode();

        var token = await response.Content.ReadFromJsonAsync<Token>();
        if (token != null && !string.IsNullOrEmpty(token.AccessToken))
        {
            SecureStorage.SaveToken(token.AccessToken);
            TokenChanged?.Invoke(this, EventArgs.Empty);
        }

        return token ?? throw new InvalidOperationException("Registration failed");
    }
}
```

**WinUI 3 View:**

```xml
<!-- Views/RegisterPage.xaml -->
<Page x:Class="AnalystApp.Views.RegisterPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <Grid MaxWidth="400" HorizontalAlignment="Center" VerticalAlignment="Center">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <TextBlock Text="ANALYST"
                   FontFamily="{StaticResource SyneFont}"
                   FontSize="36" FontWeight="ExtraBold"
                   Foreground="{ThemeResource PotomacTextBrush}"
                   HorizontalAlignment="Center" Margin="0,0,0,8"/>

        <TextBlock Text="BY POTOMAC"
                   FontFamily="{StaticResource SyneFont}"
                   FontSize="14" FontWeight="Bold"
                   Foreground="{ThemeResource PotomacAccentBrush}"
                   HorizontalAlignment="Center" Margin="0,0,0,32"/>

        <TextBox x:Name="NameBox" PlaceholderText="Full Name"
                 Grid.Row="2" Margin="0,0,0,16"/>

        <TextBox x:Name="EmailBox" PlaceholderText="Email"
                 Grid.Row="3" Margin="0,0,0,16"/>

        <PasswordBox x:Name="PasswordBox" PlaceholderText="Password"
                     Grid.Row="4" Margin="0,0,0,24"/>

        <Button x:Name="RegisterButton" Content="REGISTER"
                Style="{StaticResource PotomacPrimaryButtonStyle}"
                Grid.Row="5" Click="RegisterButton_Click"/>
    </Grid>
</Page>
```

```csharp
// Views/RegisterPage.xaml.cs
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using AnalystApp.Services;

namespace AnalystApp.Views;

public sealed partial class RegisterPage : Page
{
    private readonly ApiService _api = App.GetService<ApiService>();

    public RegisterPage()
    {
        InitializeComponent();
    }

    private async void RegisterButton_Click(object sender, RoutedEventArgs e)
    {
        RegisterButton.IsEnabled = false;

        try
        {
            var token = await _api.RegisterAsync(
                EmailBox.Text,
                PasswordBox.Password,
                NameBox.Text
            );

            if (!string.IsNullOrEmpty(token.AccessToken))
            {
                Frame.Navigate(typeof(MainPage));
            }
            else
            {
                // Email confirmation required
                var dialog = new ContentDialog
                {
                    Title = "Check Your Email",
                    Content = "A confirmation email has been sent. Please verify your email before logging in.",
                    CloseButtonText = "OK",
                    XamlRoot = XamlRoot
                };
                await dialog.ShowAsync();
                Frame.Navigate(typeof(LoginPage));
            }
        }
        catch (Exception ex)
        {
            var dialog = new ContentDialog
            {
                Title = "Registration Failed",
                Content = ex.Message,
                CloseButtonText = "OK",
                XamlRoot = XamlRoot
            };
            await dialog.ShowAsync();
        }
        finally
        {
            RegisterButton.IsEnabled = true;
        }
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

**C# Implementation:**

```csharp
public async Task<Token> LoginAsync(string email, string password)
{
    var request = new { email, password };

    var response = await _httpClient.PostAsJsonAsync("/auth/login", request);
    response.EnsureSuccessStatusCode();

    var token = await response.Content.ReadFromJsonAsync<Token>();
    if (token == null || string.IsNullOrEmpty(token.AccessToken))
        throw new InvalidOperationException("Login failed");

    SecureStorage.SaveToken(token.AccessToken);
    TokenChanged?.Invoke(this, EventArgs.Empty);

    return token;
}
```

**WinUI 3 Login View:**

```xml
<!-- Views/LoginPage.xaml -->
<Page x:Class="AnalystApp.Views.LoginPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="520"/>
        </Grid.ColumnDefinitions>

        <!-- Branding Panel -->
        <Grid Grid.Column="0" Background="{ThemeResource PotomacBackgroundBrush}">
            <Grid.Background>
                <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                    <GradientStop Color="#0A0A0B" Offset="0"/>
                    <GradientStop Color="#0D1117" Offset="0.5"/>
                    <GradientStop Color="#0A0A0B" Offset="1"/>
                </LinearGradientBrush>
            </Grid.Background>

            <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
                <Grid Width="110" Height="110" CornerRadius="28"
                      Background="{ThemeResource PotomacAccentDimBrush}">
                    <Image Source="/Assets/potomac-icon.png"
                           Width="70" Height="70"/>
                </Grid>

                <TextBlock Text="ANALYST"
                           FontFamily="{StaticResource SyneFont}"
                           FontSize="52" FontWeight="ExtraBold"
                           HorizontalAlignment="Center" Margin="0,24,0,0"/>

                <TextBlock Text="BY POTOMAC"
                           FontSize="17" FontWeight="Bold"
                           Foreground="{ThemeResource PotomacAccentBrush}"
                           HorizontalAlignment="Center" Margin="0,8,0,36"/>

                <TextBlock Text="BREAK THE STATUS QUO"
                           FontFamily="{StaticResource SyneFont}"
                           FontSize="30" FontWeight="ExtraBold"
                           Foreground="{ThemeResource PotomacAccentBrush}"
                           HorizontalAlignment="Center" TextAlignment="Center"/>
            </StackPanel>
        </Grid>

        <!-- Form Panel -->
        <Grid Grid.Column="1" Background="{ThemeResource PotomacCardBrush}"
              Padding="64,72">
            <StackPanel VerticalAlignment="Center" MaxWidth="380">
                <TextBlock Text="Welcome Back"
                           FontSize="30" FontWeight="ExtraBold" Margin="0,0,0,8"/>

                <TextBlock Text="Sign in to continue to your dashboard"
                           Foreground="{ThemeResource PotomacTextMutedBrush}"
                           Margin="0,0,0,28"/>

                <TextBox x:Name="EmailBox"
                         PlaceholderText="you@example.com"
                         Margin="0,0,0,24"/>

                <PasswordBox x:Name="PasswordBox"
                             PlaceholderText="Enter your password"
                             Margin="0,0,0,8"/>

                <Button Content="Forgot password?"
                        Style="{StaticResource PotomacTextButtonStyle}"
                        HorizontalAlignment="Right" Margin="0,0,0,28"
                        Click="ForgotPassword_Click"/>

                <Button x:Name="LoginButton" Content="SIGN IN"
                        Style="{StaticResource PotomacPrimaryButtonStyle}"
                        HorizontalAlignment="Stretch" Margin="0,0,0,36"
                        Click="LoginButton_Click"/>

                <TextBlock Text="OR" HorizontalAlignment="Center"
                           Foreground="{ThemeResource PotomacTextMutedBrush}"
                           Margin="0,0,0,36"/>

                <TextBlock Text="Don't have an account?"
                           HorizontalAlignment="Center" Margin="0,0,0,8"/>

                <Button Content="CREATE ONE"
                        Style="{StaticResource PotomacSecondaryButtonStyle}"
                        HorizontalAlignment="Center"
                        Click="GoToRegister_Click"/>
            </StackPanel>
        </Grid>
    </Grid>
</Page>
```

### Logout

```
POST /auth/logout
```

### Get Current User

```
GET /auth/me
```

### Update User Profile

```
PUT /auth/me
```

### Update API Keys

```
PUT /auth/api-keys
```

### Get API Keys Status

```
GET /auth/api-keys
```

### Forgot Password

```
POST /auth/forgot-password
```

### Reset Password

```
POST /auth/reset-password
```

### Change Password

```
PUT /auth/change-password
```

### Refresh Token

```
POST /auth/refresh-token
```

### Admin User Management

```
GET  /auth/admin/users
POST /auth/admin/users/{user_id}/make-admin
POST /auth/admin/users/{user_id}/revoke-admin
POST /auth/admin/users/{user_id}/deactivate
POST /auth/admin/users/{user_id}/activate
```

---

## 3. Chat & Conversations

### List Conversations

```
GET /chat/conversations
```

**C#:**

```csharp
public async Task<List<Conversation>> GetConversationsAsync()
{
    return await _httpClient.GetFromJsonAsync<List<Conversation>>("/chat/conversations")
        ?? new List<Conversation>();
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

### Get Messages

```
GET /chat/conversations/{conversation_id}/messages
```

### Rename Conversation

```
PATCH /chat/conversations/{conversation_id}
```

### Delete Conversation

```
DELETE /chat/conversations/{conversation_id}
```

### Chat Agent (Streaming)

```
POST /chat/agent
```

This is the main chat endpoint with full agent capabilities.

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

**C# Streaming Implementation:**

```csharp
// Services/ApiService.Chat.cs
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;

namespace AnalystApp.Services;

public partial class ApiService
{
    public async IAsyncEnumerable<StreamChunk> StreamChatAsync(
        string content,
        string? conversationId = null,
        string model = "claude-sonnet-4-6",
        string? skillSlug = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct = default)
    {
        var request = new
        {
            content,
            conversation_id = conversationId,
            model,
            thinking_mode = (string?)null,
            thinking_budget = (int?)null,
            thinking_effort = "medium",
            skill_slug = skillSlug,
            use_prompt_caching = true,
            max_iterations = 5,
            pin_model_version = false
        };

        using var httpRequest = new HttpRequestMessage(HttpMethod.Post, "/chat/agent")
        {
            Content = JsonContent.Create(request)
        };

        var response = await _httpClient.SendAsync(
            httpRequest,
            HttpCompletionOption.ResponseHeadersRead,
            ct
        );
        response.EnsureSuccessStatusCode();

        using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream);

        while (!reader.EndOfStream && !ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (string.IsNullOrWhiteSpace(line)) continue;

            yield return ParseStreamLine(line);
        }
    }

    private StreamChunk ParseStreamLine(string line)
    {
        // Vercel AI SDK Data Stream Protocol:
        // 0:"text chunk"
        // 2:[{...}]  ← data parts
        // 3:"error"
        // d:{finishReason, usage}

        if (line.StartsWith("0:"))
        {
            var text = line[2..].Trim('"');
            return new StreamChunk { Type = StreamChunkType.Text, Text = text };
        }
        else if (line.StartsWith("2:"))
        {
            var json = line[2..];
            try
            {
                var data = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                return new StreamChunk { Type = StreamChunkType.Data, Data = data };
            }
            catch { return new StreamChunk { Type = StreamChunkType.Data, RawData = json }; }
        }
        else if (line.StartsWith("3:"))
        {
            var error = line[2..].Trim('"');
            return new StreamChunk { Type = StreamChunkType.Error, Text = error };
        }
        else if (line.StartsWith("d:"))
        {
            var json = line[2..];
            try
            {
                var data = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                return new StreamChunk { Type = StreamChunkType.Finish, Data = data };
            }
            catch { return new StreamChunk { Type = StreamChunkType.Finish }; }
        }

        return new StreamChunk { Type = StreamChunkType.Unknown, RawData = line };
    }
}

public enum StreamChunkType { Text, Data, Error, Finish, Unknown }

public class StreamChunk
{
    public StreamChunkType Type { get; set; }
    public string? Text { get; set; }
    public Dictionary<string, object>? Data { get; set; }
    public string? RawData { get; set; }
}
```

**WinUI 3 Chat ViewModel:**

```csharp
// ViewModels/ChatViewModel.cs
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using AnalystApp.Services;
using AnalystApp.Models;
using System.Collections.ObjectModel;

namespace AnalystApp.ViewModels;

public partial class ChatViewModel : ObservableObject
{
    private readonly ApiService _api;

    [ObservableProperty] private ObservableCollection<ChatMessage> messages = new();
    [ObservableProperty] private string currentResponse = string.Empty;
    [ObservableProperty] private bool isStreaming;
    [ObservableProperty] private string? errorMessage;
    [ObservableProperty] private string? conversationId;
    [ObservableProperty] private string inputText = string.Empty;
    [ObservableProperty] private string selectedModel = "claude-sonnet-4-6";

    public ChatViewModel(ApiService api)
    {
        _api = api;
    }

    [RelayCommand]
    private async Task SendMessageAsync()
    {
        if (string.IsNullOrWhiteSpace(InputText) || IsStreaming) return;

        var userMessage = new ChatMessage
        {
            Id = Guid.NewGuid().ToString(),
            Role = "user",
            Content = InputText,
            CreatedAt = DateTime.UtcNow.ToString("o"),
            ConversationId = ConversationId ?? string.Empty
        };

        Messages.Add(userMessage);
        var content = InputText;
        InputText = string.Empty;
        IsStreaming = true;
        CurrentResponse = string.Empty;
        ErrorMessage = null;

        try
        {
            await foreach (var chunk in _api.StreamChatAsync(
                content,
                ConversationId,
                SelectedModel))
            {
                switch (chunk.Type)
                {
                    case StreamChunkType.Text:
                        CurrentResponse += chunk.Text;
                        break;
                    case StreamChunkType.Data:
                        if (chunk.Data?.ContainsKey("conversation_id") == true)
                            ConversationId = chunk.Data["conversation_id"]?.ToString();
                        break;
                    case StreamChunkType.Error:
                        ErrorMessage = chunk.Text;
                        break;
                }
            }

            if (!string.IsNullOrEmpty(CurrentResponse))
            {
                Messages.Add(new ChatMessage
                {
                    Id = Guid.NewGuid().ToString(),
                    Role = "assistant",
                    Content = CurrentResponse,
                    CreatedAt = DateTime.UtcNow.ToString("o"),
                    ConversationId = ConversationId ?? string.Empty
                });
            }
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
        }
        finally
        {
            IsStreaming = false;
        }
    }

    [RelayCommand]
    private void StopStreaming()
    {
        // Cancel the streaming operation
    }
}
```

**WinUI 3 Chat View:**

```xml
<!-- Views/ChatPage.xaml -->
<Page x:Class="AnalystApp.Views.ChatPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
      xmlns:controls="using:CommunityToolkit.WinUI.UI.Controls">

    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- Messages -->
        <ScrollViewer Grid.Row="0" Padding="28,40"
                      VerticalScrollBarVisibility="Auto">
            <ItemsControl ItemsSource="{x:Bind ViewModel.Messages}">
                <ItemsControl.ItemTemplate>
                    <DataTemplate x:DataType="models:ChatMessage">
                        <Grid Margin="0,0,0,24">
                            <!-- User message -->
                            <Grid Visibility="{x:Bind IsUser}">
                                <Grid HorizontalAlignment="Right" MaxWidth="400">
                                    <Border CornerRadius="16"
                                            Background="{ThemeResource PotomacAccentDimBrush}"
                                            BorderBrush="{ThemeResource PotomacAccentBorderBrush}"
                                            BorderThickness="1" Padding="12,16">
                                        <TextBlock Text="{x:Bind Content}"
                                                   TextWrapping="Wrap"/>
                                    </Border>
                                </Grid>
                            </Grid>

                            <!-- Assistant message -->
                            <Grid Visibility="{x:Bind IsAssistant}">
                                <Grid HorizontalAlignment="Left" MaxWidth="600">
                                    <Grid.ColumnDefinitions>
                                        <ColumnDefinition Width="Auto"/>
                                        <ColumnDefinition Width="*"/>
                                    </Grid.ColumnDefinitions>

                                    <Border Grid.Column="0" CornerRadius="10"
                                            Width="32" Height="32" Margin="0,0,12,0"
                                            Background="{ThemeResource PotomacBlueDimBrush}">
                                        <Image Source="/Assets/potomac-icon.png"
                                               Width="18" Height="18"/>
                                    </Border>

                                    <StackPanel Grid.Column="1">
                                        <TextBlock Text="Yang" FontWeight="Bold" Margin="0,0,0,6"/>
                                        <Border CornerRadius="16"
                                                Background="{ThemeResource PotomacAIBubbleBrush}"
                                                BorderBrush="{ThemeResource PotomacBorderBrush}"
                                                BorderThickness="1" Padding="14,18">
                                            <TextBlock Text="{x:Bind Content}"
                                                       TextWrapping="Wrap"/>
                                        </Border>
                                    </StackPanel>
                                </Grid>
                            </Grid>
                        </Grid>
                    </DataTemplate>
                </ItemsControl.ItemTemplate>
            </ItemsControl>

            <!-- Streaming indicator -->
            <StackPanel Visibility="{x:Bind ViewModel.IsStreaming, Converter={StaticResource BoolToVisibility}}"
                        Orientation="Horizontal" Spacing="8" Margin="0,0,0,24">
                <ProgressRing IsActive="True" Width="18" Height="18"/>
                <TextBlock Text="Yang is thinking..."
                           Foreground="{ThemeResource PotomacTextMutedBrush}"/>
            </StackPanel>
        </ScrollViewer>

        <!-- Input Bar -->
        <Grid Grid.Row="1" Padding="24,14"
              Background="{ThemeResource PotomacBackgroundBrush}">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <!-- Accent line -->
            <Rectangle Grid.Row="0" Height="1" Margin="0,0,0,12">
                <Rectangle.Fill>
                    <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
                        <GradientStop Color="Transparent" Offset="0"/>
                        <GradientStop Color="#60A5FA" Offset="0.4"/>
                        <GradientStop Color="#1E40AF" Offset="0.7"/>
                        <GradientStop Color="Transparent" Offset="1"/>
                    </LinearGradientBrush>
                </Rectangle.Fill>
            </Rectangle>

            <Grid Grid.Row="1">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>

                <Button Grid.Column="0" Content="&#xE7C3;"
                        FontFamily="{StaticResource SymbolThemeFontFamily}"
                        Style="{StaticResource PotomacIconButtonStyle}" Margin="0,0,12,0"/>

                <TextBox Grid.Column="1" x:Name="InputBox"
                         PlaceholderText="Type a message..."
                         Text="{x:Bind ViewModel.InputText, Mode=TwoWay}"
                         VerticalContentAlignment="Center"/>

                <Button Grid.Column="2" Content="&#xE7C7;"
                        FontFamily="{StaticResource SymbolThemeFontFamily}"
                        Style="{StaticResource PotomacAccentIconButtonStyle}" Margin="12,0,0,0"
                        Command="{x:Bind ViewModel.SendMessageCommand}"/>
            </Grid>
        </Grid>
    </Grid>
</Page>
```

### List Models

```
GET /chat/models
```

### Text-to-Speech

```
POST /chat/tts
```

### List TTS Voices

```
GET /chat/tts/voices
```

---

## 4. AI SDK Streaming

### AI Status

```
GET /ai/status
```

### List Invokable Skills

```
GET /ai/skills
```

### Get Skill Detail

```
GET /ai/skills/{slug}
```

### Invoke Skill (Streaming)

```
POST /ai/skills/{slug}
```

**C#:**

```csharp
public async IAsyncEnumerable<StreamChunk> InvokeSkillAsync(
    string slug,
    string message,
    [EnumeratorCancellation] CancellationToken ct = default)
{
    var request = new
    {
        message,
        system_prompt = (string?)null,
        extra_context = "",
        conversation_history = (List<Dictionary<string, string>>?)null,
        max_tokens = (int?)null
    };

    using var httpRequest = new HttpRequestMessage(HttpMethod.Post, $"/ai/skills/{slug}")
    {
        Content = JsonContent.Create(request)
    };

    var response = await _httpClient.SendAsync(
        httpRequest, HttpCompletionOption.ResponseHeadersRead, ct);
    response.EnsureSuccessStatusCode();

    using var stream = await response.Content.ReadAsStreamAsync(ct);
    using var reader = new StreamReader(stream);

    while (!reader.EndOfStream && !ct.IsCancellationRequested)
    {
        var line = await reader.ReadLineAsync(ct);
        if (!string.IsNullOrWhiteSpace(line))
            yield return ParseStreamLine(line);
    }
}
```

---

## 5. AFL Code Generation

### Generate AFL

```
POST /afl/generate
```

**C#:**

```csharp
public async Task<AflGenerateResponse> GenerateAflAsync(
    string prompt,
    string strategyType = "standalone",
    BacktestSettingsInput? settings = null,
    bool stream = false)
{
    var request = new
    {
        prompt,
        strategy_type = strategyType,
        backtest_settings = settings,
        conversation_id = (string?)null,
        answers = (Dictionary<string, string>?)null,
        stream,
        uploaded_file_ids = (List<string>?)null,
        kb_context = (string?)null,
        thinking_mode = (string?)null,
        thinking_budget = (int?)null
    };

    if (stream)
    {
        // Return streaming response
        // ...
    }

    var response = await _httpClient.PostAsJsonAsync("/afl/generate", request);
    response.EnsureSuccessStatusCode();
    return await response.Content.ReadFromJsonAsync<AflGenerateResponse>()
        ?? throw new InvalidOperationException("AFL generation failed");
}

public class AflGenerateResponse
{
    [JsonPropertyName("code")]
    public string Code { get; set; } = string.Empty;

    [JsonPropertyName("afl_code")]
    public string? AflCode { get; set; }

    [JsonPropertyName("explanation")]
    public string? Explanation { get; set; }

    [JsonPropertyName("stats")]
    public Dictionary<string, object>? Stats { get; set; }
}

public class BacktestSettingsInput
{
    [JsonPropertyName("initial_equity")]
    public double InitialEquity { get; set; } = 100000;

    [JsonPropertyName("position_size")]
    public string PositionSize { get; set; } = "100";

    [JsonPropertyName("max_positions")]
    public int MaxPositions { get; set; } = 10;

    [JsonPropertyName("commission")]
    public double Commission { get; set; } = 0.0005;

    [JsonPropertyName("trade_delays")]
    public int[] TradeDelays { get; set; } = { 0, 0, 0, 0 };

    [JsonPropertyName("margin_requirement")]
    public double MarginRequirement { get; set; } = 100;
}
```

### Optimize / Debug / Explain / Validate

```
POST /afl/optimize
POST /afl/debug
POST /afl/explain
POST /afl/validate
```

### AFL Codes CRUD

```
GET    /afl/codes?limit=50
GET    /afl/codes/{code_id}
DELETE /afl/codes/{code_id}
```

### AFL History

```
POST   /afl/history
GET    /afl/history
DELETE /afl/history/{id}
```

### AFL File Upload

```
POST   /afl/upload
GET    /afl/files
GET    /afl/files/{id}
DELETE /afl/files/{id}
```

### Settings Presets

```
POST   /afl/settings/presets
GET    /afl/settings/presets
GET    /afl/settings/presets/{id}
PUT    /afl/settings/presets/{id}
DELETE /afl/settings/presets/{id}
POST   /afl/settings/presets/{id}/set-default
```

---

## 6. Knowledge Base / Brain

### Upload Document

```
POST /brain/upload
```

**C# (Multipart):**

```csharp
public async Task<Dictionary<string, object>> UploadDocumentAsync(
    StorageFile file,
    string? title = null,
    string category = "general")
{
    using var content = new MultipartFormDataContent();
    using var fileStream = await file.OpenStreamForReadAsync();
    var fileContent = new StreamContent(fileStream);
    fileContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(
        file.ContentType ?? "application/octet-stream"
    );
    content.Add(fileContent, "file", file.Name);

    if (title != null)
        content.Add(new StringContent(title), "title");
    content.Add(new StringContent(category), "category");

    var response = await _httpClient.PostAsync("/brain/upload", content);
    response.EnsureSuccessStatusCode();

    return await response.Content.ReadFromJsonAsync<Dictionary<string, object>>()
        ?? new Dictionary<string, object>();
}
```

### Batch Upload / Upload Text / Search

```
POST /brain/upload-batch
POST /brain/upload-text
POST /brain/search
```

### Documents CRUD

```
GET    /brain/documents?category=strategy&limit=50
GET    /brain/documents/{id}
GET    /brain/documents/{id}/content
GET    /brain/documents/{id}/download
DELETE /brain/documents/{id}
GET    /brain/stats
```

---

## 7. File Upload

### Direct Upload

```
POST /upload/direct
```

### Upload to Conversation

```
POST /upload/conversations/{conversation_id}
```

### File Management

```
GET    /upload/files?limit=50&offset=0
GET    /upload/files/{id}
GET    /upload/files/{id}/download
DELETE /upload/files/{id}
POST   /upload/files/{id}/extract
GET    /upload/conversations/{id}/files
POST   /upload/files/{id}/link/{conv_id}
GET    /upload/info
```

---

## 8. Generated Files

```
GET /files/{id}/download
GET /files/{id}/info
GET /files/generated
```

---

## 9. Backtest Analysis

```
POST /backtest/upload
GET  /backtest/history
GET  /backtest/{id}
GET  /backtest/strategy/{id}
```

---

## 10. Researcher

```
GET  /researcher/company/{symbol}
GET  /researcher/company/{symbol}/stream
GET  /researcher/news/{symbol}?limit=20
POST /researcher/strategy-analysis
POST /researcher/comparison
GET  /researcher/macro-context
GET  /researcher/sec-filings/{symbol}
POST /researcher/generate-report
GET  /researcher/reports/{id}/export?format=pdf
GET  /researcher/search?query=AAPL&search_type=company&limit=10
GET  /researcher/trending?limit=10
GET  /researcher/health
```

---

## 11. Skills

```
GET /skills?category=market_analysis&include_builtins=true
GET /skills/categories
GET /skills/jobs
GET /skills/{slug}
```

---

## 12. YFinance Data

```
GET /yfinance/{ticker}?include=info,history&history_period=1y&history_interval=1d
GET /yfinance/{ticker}/summary
GET /yfinance/{ticker}/history?period=1y&interval=1d
```

---

## 13. SEC EDGAR

```
GET  /edgar/security/{identifier}
GET  /edgar/search?q=Apple&limit=10
GET  /edgar/company/{cik}
GET  /edgar/company/{cik}/filings?form_type=10-K&limit=20
GET  /edgar/company/{cik}/filings/{accession_number}
GET  /edgar/company/{cik}/financials
GET  /edgar/company/{cik}/concept?concept=Revenues&taxonomy=us-gaap&limit=20
GET  /edgar/ticker/{ticker}/filings
GET  /edgar/ticker/{ticker}/annual
GET  /edgar/ticker/{ticker}/quarterly
GET  /edgar/ticker/{ticker}/events
GET  /edgar/ticker/{ticker}/insider
GET  /edgar/ticker/{ticker}/proxy
GET  /edgar/ticker/{ticker}/financials
POST /edgar/search/fulltext
GET  /edgar/tickers?exchange=Nasdaq&limit=100
```

---

## 14. Background Tasks

```
POST   /tasks
GET    /tasks
GET    /tasks/{id}
POST   /tasks/{id}/cancel
DELETE /tasks/{id}
DELETE /tasks
```

---

## 15. Consensus

```
POST /consensus/validate
GET  /consensus/models
```

---

## 16. Training

```
POST /train/feedback
GET  /train/feedback/my?limit=50
GET  /train/feedback/{id}
POST /train/test
GET  /train/effectiveness
POST /train/suggest
GET  /train/suggestions/my?limit=50
POST /train/quick-learn
GET  /train/analytics/learning-curve?days=30
GET  /train/analytics/popular-patterns?limit=10
GET  /train/knowledge/search?query=RSI&category=afl&limit=10
GET  /train/knowledge/categories
GET  /train/knowledge/types
GET  /train/stats
```

---

## 17. Admin

```
GET    /admin/status
POST   /admin/make-admin/{id}
POST   /admin/revoke-admin/{id}
POST   /admin/train
POST   /admin/train/quick
POST   /admin/train/correction
POST   /admin/train/batch
GET    /admin/training
GET    /admin/training/{id}
PUT    /admin/training/{id}
DELETE /admin/training/{id}
POST   /admin/training/{id}/toggle
GET    /admin/training/stats/overview
GET    /admin/training/export/all
GET    /admin/training/context/preview
GET    /admin/users
GET    /admin/users/{id}
PUT    /admin/users/{id}
DELETE /admin/users/{id}
POST   /admin/users/{id}/restore
GET    /admin/config
PUT    /admin/config
POST   /admin/config/add-admin-email
GET    /admin/feedback
GET    /admin/feedback/{id}
POST   /admin/feedback/{id}/review
GET    /admin/suggestions
GET    /admin/suggestions/{id}
POST   /admin/suggestions/{id}/review
POST   /admin/suggestions/{id}/approve
POST   /admin/suggestions/{id}/reject
GET    /admin/analytics/overview?days=30
GET    /admin/analytics/trends?days=30
GET    /admin/analytics/engagement?days=30
GET    /admin/audit-logs
GET    /admin/health/system
POST   /admin/maintenance/toggle?enable=true
GET    /admin/export/users
GET    /admin/export/feedback
GET    /admin/export/training
```

---

## 18. Presentation Generation

```
POST /api/generate-presentation
POST /api/generate-presentation/test
```

---

## 19. KB Admin Bulk Upload

```
POST   /kb-admin/bulk-upload
GET    /kb-admin/list?category=research&limit=100
DELETE /kb-admin/documents/{id}
POST   /kb-admin/upload-preparsed
GET    /kb-admin/stats
```

---

## 20. Health & Diagnostics

```
GET /health/
GET /health/db
GET /health/config
GET /health/migrations
GET /
```

---

## 21. Rate Limiting

The API enforces **120 requests per minute per IP address**.

**C# Handling with Polly:**

```csharp
using Polly;
using Polly.Extensions.Http;

// In DI setup:
services.AddHttpClient<ApiService>(client =>
{
    client.BaseAddress = new Uri(ApiConfig.BaseUrl);
    client.Timeout = TimeSpan.FromSeconds(ApiConfig.TimeoutSeconds);
})
.AddPolicyHandler(HttpPolicyExtensions
    .HandleTransientHttpError()
    .OrResult(msg => msg.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
    .WaitAndRetryAsync(
        retryCount: 3,
        sleepDurationProvider: (retryCount, response, _) =>
        {
            if (response.Result?.Headers.RetryAfter?.Delta is TimeSpan delta)
                return delta;
            return TimeSpan.FromSeconds(Math.Pow(2, retryCount));
        }
    )
);
```

---

## 22. Error Handling

```csharp
// Services/ApiException.cs
namespace AnalystApp.Services;

public class ApiException : Exception
{
    public int StatusCode { get; }
    public string? Detail { get; }

    public ApiException(int statusCode, string? detail)
        : base(detail ?? $"API error {statusCode}")
    {
        StatusCode = statusCode;
        Detail = detail;
    }
}

// Enhanced request with error mapping
public async Task<T> RequestAsync<T>(string endpoint, HttpMethod method, object? body = null)
{
    var request = new HttpRequestMessage(method, endpoint);
    if (body != null)
        request.Content = JsonContent.Create(body);

    var response = await _httpClient.SendAsync(request);
    var content = await response.Content.ReadAsStringAsync();

    if (!response.IsSuccessStatusCode)
    {
        string? detail = null;
        try
        {
            var error = JsonSerializer.Deserialize<Dictionary<string, string>>(content);
            error?.TryGetValue("detail", out detail);
        }
        catch { }

        throw response.StatusCode switch
        {
            System.Net.HttpStatusCode.Unauthorized => new ApiException(401, "Authentication required"),
            System.Net.HttpStatusCode.Forbidden => new ApiException(403, "Access denied"),
            System.Net.HttpStatusCode.NotFound => new ApiException(404, detail ?? $"{endpoint} not found"),
            System.Net.HttpStatusCode.TooManyRequests => new ApiException(429, "Rate limited. Try again later."),
            _ => new ApiException((int)response.StatusCode, detail ?? content)
        };
    }

    return JsonSerializer.Deserialize<T>(content)
        ?? throw new InvalidOperationException("Deserialization failed");
}
```

---

## 23. MVVM Architecture

### App.xaml.cs

```csharp
// App.xaml.cs
using Microsoft.Extensions.DependencyInjection;
using AnalystApp.Services;
using AnalystApp.ViewModels;
using AnalystApp.Views;

namespace AnalystApp;

public partial class App : Application
{
    public static IServiceProvider Services { get; private set; } = null!;
    public static T GetService<T>() where T : class => Services.GetRequiredService<T>();

    public App()
    {
        InitializeComponent();

        var services = new ServiceCollection();
        ConfigureServices(services);
        Services = services.BuildServiceProvider();
    }

    private static void ConfigureServices(IServiceCollection services)
    {
        // HTTP Client with retry policy
        services.AddHttpClient<ApiService>(client =>
        {
            client.BaseAddress = new Uri(ApiConfig.BaseUrl);
            client.Timeout = TimeSpan.FromSeconds(ApiConfig.TimeoutSeconds);
        })
        .AddPolicyHandler(HttpPolicyExtensions
            .HandleTransientHttpError()
            .WaitAndRetryAsync(3, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)))
        );

        // ViewModels
        services.AddTransient<ChatViewModel>();
        services.AddTransient<DashboardViewModel>();
        services.AddTransient<AflViewModel>();
        services.AddTransient<SettingsViewModel>();

        // Services
        services.AddSingleton<INavigationService, NavigationService>();
        services.AddSingleton<IThemeService, ThemeService>();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var window = new MainWindow();
        window.Activate();
    }
}
```

### MainWindow.xaml

```xml
<!-- MainWindow.xaml -->
<Window x:Class="AnalystApp.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Analyst by Potomac">

    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="Auto"/>
            <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>

        <!-- Sidebar -->
        <Grid Grid.Column="0" Width="256"
              Background="{ThemeResource PotomacSidebarBrush}">
            <local:NavigationView x:Name="NavView"
                                  ItemInvoked="NavView_ItemInvoked"/>
        </Grid>

        <!-- Content -->
        Frame x:Name="ContentFrame" Grid.Column="1"/>
    </Grid>
</Window>
```

---

## 24. Complete Networking Layer

```csharp
// Services/ApiService.cs
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace AnalystApp.Services;

public partial class ApiService : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly JsonSerializerOptions _jsonOptions;

    public event EventHandler? TokenChanged;

    public ApiService(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _jsonOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            PropertyNameCaseInsensitive = true
        };

        // Restore token
        var token = SecureStorage.GetToken();
        if (!string.IsNullOrEmpty(token))
            SetAuthToken(token);
    }

    public void SetAuthToken(string token)
    {
        _httpClient.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue("Bearer", token);
    }

    public void ClearAuthToken()
    {
        _httpClient.DefaultRequestHeaders.Authorization = null;
        SecureStorage.ClearToken();
        TokenChanged?.Invoke(this, EventArgs.Empty);
    }

    public bool IsAuthenticated =>
        _httpClient.DefaultRequestHeaders.Authorization != null;

    // ── Generic request helpers ──

    public async Task<T> GetAsync<T>(string endpoint)
    {
        var response = await _httpClient.GetAsync(endpoint);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(_jsonOptions)
            ?? throw new InvalidOperationException($"Failed to deserialize {endpoint}");
    }

    public async Task<T> PostAsync<T>(string endpoint, object body)
    {
        var response = await _httpClient.PostAsJsonAsync(endpoint, body, _jsonOptions);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(_jsonOptions)
            ?? throw new InvalidOperationException($"Failed to deserialize {endpoint}");
    }

    public async Task PostAsync(string endpoint, object body)
    {
        var response = await _httpClient.PostAsJsonAsync(endpoint, body, _jsonOptions);
        response.EnsureSuccessStatusCode();
    }

    public async Task<T> PutAsync<T>(string endpoint, object body)
    {
        var response = await _httpClient.PutAsJsonAsync(endpoint, body, _jsonOptions);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(_jsonOptions)
            ?? throw new InvalidOperationException($"Failed to deserialize {endpoint}");
    }

    public async Task DeleteAsync(string endpoint)
    {
        var response = await _httpClient.DeleteAsync(endpoint);
        response.EnsureSuccessStatusCode();
    }

    // ── File upload ──

    public async Task<T> UploadFileAsync<T>(string endpoint, string filePath,
        Dictionary<string, string>? fields = null)
    {
        using var content = new MultipartFormDataContent();
        using var fileStream = File.OpenRead(filePath);
        content.Add(new StreamContent(fileStream), "file", Path.GetFileName(filePath));

        if (fields != null)
        {
            foreach (var (key, value) in fields)
                content.Add(new StringContent(value), key);
        }

        var response = await _httpClient.PostAsync(endpoint, content);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(_jsonOptions)
            ?? throw new InvalidOperationException($"Failed to upload file");
    }

    public void Dispose()
    {
        _httpClient.Dispose();
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
| POST | `/auth/forgot-password` | No | Request reset |
| POST | `/auth/reset-password` | Yes | Reset password |
| PUT | `/auth/change-password` | Yes | Change password |
| POST | `/auth/refresh-token` | Yes | Refresh token |
| GET | `/auth/admin/users` | Yes | List users |
| POST | `/auth/admin/users/{id}/make-admin` | Yes | Make admin |
| POST | `/auth/admin/users/{id}/revoke-admin` | Yes | Revoke admin |
| POST | `/auth/admin/users/{id}/deactivate` | Yes | Deactivate |
| POST | `/auth/admin/users/{id}/activate` | Yes | Activate |
| GET | `/chat/conversations` | Yes | List conversations |
| POST | `/chat/conversations` | Yes | Create conversation |
| GET | `/chat/conversations/{id}/messages` | Yes | Get messages |
| PATCH | `/chat/conversations/{id}` | Yes | Rename conversation |
| DELETE | `/chat/conversations/{id}` | Yes | Delete conversation |
| POST | `/chat/agent` | Yes | Chat agent (streaming) |
| GET | `/chat/models` | Yes | List models |
| POST | `/chat/tts` | Yes | Text-to-speech |
| GET | `/chat/tts/voices` | No | List voices |
| GET | `/ai/status` | No | AI status |
| GET | `/ai/skills` | Yes | List skills |
| GET | `/ai/skills/{slug}` | Yes | Skill detail |
| POST | `/ai/skills/{slug}` | Yes | Invoke skill |
| POST | `/afl/generate` | Yes | Generate AFL |
| POST | `/afl/optimize` | Yes | Optimize AFL |
| POST | `/afl/debug` | Yes | Debug AFL |
| POST | `/afl/explain` | Yes | Explain AFL |
| POST | `/afl/validate` | No | Validate AFL |
| GET | `/afl/codes` | Yes | List codes |
| GET | `/afl/codes/{id}` | Yes | Get code |
| DELETE | `/afl/codes/{id}` | Yes | Delete code |
| POST | `/afl/history` | Yes | Save history |
| GET | `/afl/history` | Yes | Get history |
| DELETE | `/afl/history/{id}` | Yes | Delete history |
| POST | `/afl/upload` | Yes | Upload file |
| GET | `/afl/files` | Yes | List files |
| GET | `/afl/files/{id}` | Yes | Get file |
| DELETE | `/afl/files/{id}` | Yes | Delete file |
| POST | `/afl/settings/presets` | Yes | Save preset |
| GET | `/afl/settings/presets` | Yes | List presets |
| GET | `/afl/settings/presets/{id}` | Yes | Get preset |
| PUT | `/afl/settings/presets/{id}` | Yes | Update preset |
| DELETE | `/afl/settings/presets/{id}` | Yes | Delete preset |
| POST | `/afl/settings/presets/{id}/set-default` | Yes | Set default |
| POST | `/brain/upload` | Yes | Upload doc |
| POST | `/brain/upload-batch` | Yes | Batch upload |
| POST | `/brain/upload-text` | Yes | Upload text |
| POST | `/brain/search` | Yes | Search KB |
| GET | `/brain/documents` | Yes | List docs |
| GET | `/brain/documents/{id}` | Yes | Get doc |
| GET | `/brain/documents/{id}/content` | Yes | Get content |
| GET | `/brain/documents/{id}/download` | Yes | Download doc |
| DELETE | `/brain/documents/{id}` | Yes | Delete doc |
| GET | `/brain/stats` | Yes | KB stats |
| POST | `/upload/direct` | Yes | Direct upload |
| POST | `/upload/conversations/{id}` | Yes | Upload to conv |
| GET | `/upload/files` | Yes | List files |
| GET | `/upload/files/{id}` | Yes | Get file |
| GET | `/upload/files/{id}/download` | Yes | Download |
| DELETE | `/upload/files/{id}` | Yes | Delete file |
| POST | `/upload/files/{id}/extract` | Yes | Extract text |
| GET | `/upload/conversations/{id}/files` | Yes | Conv files |
| POST | `/upload/files/{id}/link/{conv_id}` | Yes | Link file |
| GET | `/upload/info` | No | Storage info |
| GET | `/files/{id}/download` | Yes | Download file |
| GET | `/files/{id}/info` | Yes | File info |
| GET | `/files/generated` | Yes | List generated |
| POST | `/backtest/upload` | Yes | Upload backtest |
| GET | `/backtest/history` | Yes | List backtests |
| GET | `/backtest/{id}` | Yes | Get backtest |
| GET | `/backtest/strategy/{id}` | Yes | Strategy backtests |
| GET | `/researcher/company/{symbol}` | Yes | Research |
| GET | `/researcher/company/{symbol}/stream` | Yes | Research stream |
| GET | `/researcher/news/{symbol}` | Yes | News |
| POST | `/researcher/strategy-analysis` | Yes | Strategy analysis |
| POST | `/researcher/comparison` | Yes | Peer comparison |
| GET | `/researcher/macro-context` | Yes | Macro context |
| GET | `/researcher/sec-filings/{symbol}` | Yes | SEC filings |
| POST | `/researcher/generate-report` | Yes | Generate report |
| GET | `/researcher/reports/{id}/export` | Yes | Export report |
| GET | `/researcher/search` | Yes | Search |
| GET | `/researcher/trending` | Yes | Trending |
| GET | `/researcher/health` | No | Health |
| GET | `/skills` | Yes | List skills |
| GET | `/skills/categories` | Yes | Categories |
| GET | `/skills/jobs` | Yes | Jobs |
| GET | `/skills/{slug}` | Yes | Skill detail |
| GET | `/yfinance/{ticker}` | Yes | YFinance data |
| GET | `/yfinance/{ticker}/summary` | Yes | Summary |
| GET | `/yfinance/{ticker}/history` | Yes | History |
| GET | `/edgar/security/{identifier}` | Yes | Security lookup |
| GET | `/edgar/search` | Yes | Search companies |
| GET | `/edgar/company/{cik}` | Yes | Company info |
| GET | `/edgar/company/{cik}/filings` | Yes | Filings |
| GET | `/edgar/company/{cik}/filings/{accn}` | Yes | Filing docs |
| GET | `/edgar/company/{cik}/financials` | Yes | Financials |
| GET | `/edgar/company/{cik}/concept` | Yes | XBRL concept |
| GET | `/edgar/ticker/{ticker}/filings` | Yes | Ticker filings |
| GET | `/edgar/ticker/{ticker}/annual` | Yes | 10-K |
| GET | `/edgar/ticker/{ticker}/quarterly` | Yes | 10-Q |
| GET | `/edgar/ticker/{ticker}/events` | Yes | 8-K |
| GET | `/edgar/ticker/{ticker}/insider` | Yes | Form 4 |
| GET | `/edgar/ticker/{ticker}/proxy` | Yes | Proxy |
| GET | `/edgar/ticker/{ticker}/financials` | Yes | Financials |
| POST | `/edgar/search/fulltext` | Yes | Full-text |
| GET | `/edgar/tickers` | Yes | All tickers |
| POST | `/tasks` | Yes | Submit task |
| GET | `/tasks` | Yes | List tasks |
| GET | `/tasks/{id}` | Yes | Get task |
| POST | `/tasks/{id}/cancel` | Yes | Cancel task |
| DELETE | `/tasks/{id}` | Yes | Dismiss task |
| DELETE | `/tasks` | Yes | Clear completed |
| POST | `/consensus/validate` | Yes | Consensus |
| GET | `/consensus/models` | Yes | Models |
| POST | `/train/feedback` | Yes | Feedback |
| GET | `/train/feedback/my` | Yes | My feedback |
| GET | `/train/feedback/{id}` | Yes | Feedback detail |
| POST | `/train/test` | Yes | Test training |
| GET | `/train/effectiveness` | Yes | Effectiveness |
| POST | `/train/suggest` | Yes | Suggest |
| GET | `/train/suggestions/my` | Yes | My suggestions |
| POST | `/train/quick-learn` | Yes | Quick learn |
| GET | `/train/analytics/learning-curve` | Yes | Learning curve |
| GET | `/train/analytics/popular-patterns` | Yes | Patterns |
| GET | `/train/knowledge/search` | Yes | Search |
| GET | `/train/knowledge/categories` | Yes | Categories |
| GET | `/train/knowledge/types` | Yes | Types |
| GET | `/train/stats` | Yes | Stats |
| GET | `/admin/status` | Yes | Admin status |
| POST | `/admin/make-admin/{id}` | Yes | Make admin |
| POST | `/admin/revoke-admin/{id}` | Yes | Revoke admin |
| POST | `/admin/train` | Yes | Add training |
| POST | `/admin/train/quick` | Yes | Quick train |
| POST | `/admin/train/correction` | Yes | Correction |
| POST | `/admin/train/batch` | Yes | Batch import |
| GET | `/admin/training` | Yes | List training |
| GET | `/admin/training/{id}` | Yes | Get training |
| PUT | `/admin/training/{id}` | Yes | Update training |
| DELETE | `/admin/training/{id}` | Yes | Delete training |
| POST | `/admin/training/{id}/toggle` | Yes | Toggle |
| GET | `/admin/training/stats/overview` | Yes | Stats |
| GET | `/admin/training/export/all` | Yes | Export |
| GET | `/admin/training/context/preview` | Yes | Preview |
| GET | `/admin/users` | Yes | List users |
| GET | `/admin/users/{id}` | Yes | Get user |
| PUT | `/admin/users/{id}` | Yes | Update user |
| DELETE | `/admin/users/{id}` | Yes | Delete user |
| POST | `/admin/users/{id}/restore` | Yes | Restore user |
| GET | `/admin/config` | Yes | Get config |
| PUT | `/admin/config` | Yes | Update config |
| POST | `/admin/config/add-admin-email` | Yes | Add admin |
| GET | `/admin/feedback` | Yes | List feedback |
| GET | `/admin/feedback/{id}` | Yes | Get feedback |
| POST | `/admin/feedback/{id}/review` | Yes | Review |
| GET | `/admin/suggestions` | Yes | List suggestions |
| GET | `/admin/suggestions/{id}` | Yes | Get suggestion |
| POST | `/admin/suggestions/{id}/review` | Yes | Review |
| POST | `/admin/suggestions/{id}/approve` | Yes | Approve |
| POST | `/admin/suggestions/{id}/reject` | Yes | Reject |
| GET | `/admin/analytics/overview` | Yes | Overview |
| GET | `/admin/analytics/trends` | Yes | Trends |
| GET | `/admin/analytics/engagement` | Yes | Engagement |
| GET | `/admin/audit-logs` | Yes | Audit logs |
| GET | `/admin/health/system` | Yes | Health |
| POST | `/admin/maintenance/toggle` | Yes | Toggle |
| GET | `/admin/export/users` | Yes | Export users |
| GET | `/admin/export/feedback` | Yes | Export feedback |
| GET | `/admin/export/training` | Yes | Export training |
| POST | `/api/generate-presentation` | Yes | Generate PPTX |
| POST | `/api/generate-presentation/test` | No | Test PPTX |
| POST | `/kb-admin/bulk-upload` | No* | Bulk upload |
| GET | `/kb-admin/list` | No* | List KB |
| DELETE | `/kb-admin/documents/{id}` | No* | Delete KB doc |
| POST | `/kb-admin/upload-preparsed` | No* | Pre-parsed |
| GET | `/kb-admin/stats` | No* | KB stats |
| GET | `/health/` | No | Health check |
| GET | `/health/db` | No | DB health |
| GET | `/health/config` | No | Config |
| GET | `/health/migrations` | No | Migrations |
| GET | `/files/{id}/preview` | Yes | Preview |
| GET | `/` | No | Root info |

> \* KB Admin endpoints use `X-Admin-Key` header instead of Bearer JWT.

---

**Last Updated:** March 2026
**API Version:** 2.0
**Base URL:** `https://developer-potomaac.up.railway.app/`
**Framework:** WinUI 3 (Windows App SDK) / .NET 8+ / C#