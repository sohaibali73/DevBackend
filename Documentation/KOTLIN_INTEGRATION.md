# Kotlin Integration Guide
Analyst by Potomac API | Android / JVM

---

## Requirements
- Android API 26+ / JVM 11+
- Kotlin 1.8+
- Dependencies:
  - OkHttp 4.10+
  - Retrofit 2.9+
  - Kotlin Coroutines
  - Moshi / Gson for JSON serialization

---

## Step 1: Dependencies Setup
Add to your `build.gradle (Module level)`:

```gradle
dependencies {
    // Networking
    implementation "com.squareup.okhttp3:okhttp:4.12.0"
    implementation "com.squareup.retrofit2:retrofit:2.9.0"
    implementation "com.squareup.retrofit2:converter-moshi:2.9.0"
    
    // Coroutines
    implementation "org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3"
    
    // JSON
    implementation "com.squareup.moshi:moshi-kotlin:1.15.0"
}
```

---

## Step 2: API Client Configuration

```kotlin
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

object PotomacApiClient {
    private const val BASE_URL = "https://developer-potomaac.up.railway.app/"
    
    private var authToken: String? = null
    
    private val okHttpClient = OkHttpClient.Builder()
        .connectTimeout(120, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val request = chain.request().newBuilder()
            authToken?.let {
                request.addHeader("Authorization", "Bearer $it")
            }
            request.addHeader("Accept", "application/json")
            chain.proceed(request.build())
        }
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        })
        .build()
    
    private val retrofit = Retrofit.Builder()
        .baseUrl(BASE_URL)
        .client(okHttpClient)
        .addConverterFactory(MoshiConverterFactory.create())
        .build()
    
    val api: PotomacApiService = retrofit.create(PotomacApiService::class.java)
    
    fun setAuthToken(token: String) {
        authToken = token
    }
    
    fun clearAuthToken() {
        authToken = null
    }
}
```

---

## Step 3: API Service Interface

```kotlin
import retrofit2.http.*
import retrofit2.Response

interface PotomacApiService {
    
    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): Response<AuthResponse>
    
    @POST("ai/chat")
    suspend fun sendChatMessage(@Body request: ChatRequest): Response<ChatResponse>
    
    @POST("afl/generate")
    suspend fun generateAFL(@Body request: AflRequest): Response<AflResponse>
    
    @GET("yfinance/quote")
    suspend fun getStockQuote(@Query("symbol") symbol: String): Response<StockQuote>
    
    @Multipart
    @POST("upload/file")
    suspend fun uploadFile(
        @Part file: MultipartBody.Part
    ): Response<UploadResponse>
    
    @Streaming
    @POST("ai/stream")
    suspend fun streamChat(@Body request: StreamRequest): Response<ResponseBody>
}
```

---

## Step 4: Data Models

```kotlin
data class LoginRequest(
    val email: String,
    val password: String
)

data class AuthResponse(
    @Json(name = "access_token") val accessToken: String,
    @Json(name = "token_type") val tokenType: String,
    @Json(name = "expires_in") val expiresIn: Int
)

data class ChatRequest(
    val message: String,
    val stream: Boolean = false
)

data class ChatResponse(
    val content: String,
    val model: String
)

data class ApiError(
    val detail: String,
    val type: String?
)
```

---

## Step 5: Authentication Usage

```kotlin
suspend fun loginUser(email: String, password: String): String? {
    return try {
        val response = PotomacApiClient.api.login(LoginRequest(email, password))
        
        if (response.isSuccessful) {
            val authResponse = response.body()
            authResponse?.accessToken?.let { token ->
                PotomacApiClient.setAuthToken(token)
                // Save token to EncryptedSharedPreferences
                TokenManager.saveToken(token)
                return token
            }
        } else {
            val error = Moshi.Builder().build().adapter(ApiError::class.java)
                .fromJson(response.errorBody()?.string())
            throw Exception(error?.detail ?: "Login failed")
        }
        null
    } catch (e: Exception) {
        null
    }
}
```

---

## Step 6: Streaming Response Handling

```kotlin
suspend fun streamChatMessage(prompt: String, onChunk: (String) -> Unit) {
    val response = PotomacApiClient.api.streamChat(StreamRequest(prompt, true))
    
    if (response.isSuccessful) {
        response.body()?.byteStream()?.bufferedReader()?.use { reader ->
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                line?.takeIf { it.startsWith("data: ") && it != "data: [DONE]" }
                    ?.substring(6)
                    ?.let { chunk ->
                        onChunk(chunk)
                    }
            }
        }
    }
}
```

---

## Step 7: Error Handling

```kotlin
sealed class ApiResult<out T> {
    data class Success<out T>(val data: T) : ApiResult<T>()
    data class Error(val message: String, val code: Int) : ApiResult<Nothing>()
    object Loading : ApiResult<Nothing>()
}

suspend fun <T> safeApiCall(call: suspend () -> Response<T>): ApiResult<T> {
    return try {
        val response = call()
        when {
            response.isSuccessful -> ApiResult.Success(response.body()!!)
            response.code() == 401 -> {
                PotomacApiClient.clearAuthToken()
                ApiResult.Error("Unauthorized", 401)
            }
            response.code() == 429 -> {
                val retryAfter = response.headers()["Retry-After"]?.toLongOrNull() ?: 60
                ApiResult.Error("Rate limit exceeded. Retry after $retryAfter seconds.", 429)
            }
            else -> ApiResult.Error("Request failed", response.code())
        }
    } catch (e: Exception) {
        ApiResult.Error(e.message ?: "Network error", -1)
    }
}
```

---

## Step 8: Jetpack Compose Example

```kotlin
@Composable
fun ChatScreen() {
    var message by remember { mutableStateOf("") }
    var response by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    
    Column(modifier = Modifier.padding(16.dp)) {
        TextField(
            value = message,
            onValueChange = { message = it },
            label = { Text("Enter message") }
        )
        
        Button(
            onClick = {
                isLoading = true
                CoroutineScope(Dispatchers.IO).launch {
                    val result = safeApiCall {
                        PotomacApiClient.api.sendChatMessage(ChatRequest(message))
                    }
                    withContext(Dispatchers.Main) {
                        isLoading = false
                        when (result) {
                            is ApiResult.Success -> response = result.data.content
                            is ApiResult.Error -> response = result.message
                        }
                    }
                }
            },
            enabled = !isLoading,
            modifier = Modifier.padding(vertical = 16.dp)
        ) {
            Text(if (isLoading) "Loading..." else "Send")
        }
        
        Text(text = response)
    }
}
```

---

## Best Practices
1.  Always use `suspend` functions with Coroutines
2.  Store auth tokens using `EncryptedSharedPreferences`
3.  Implement automatic token refresh with Authenticator
4.  Use ViewModel with `viewModelScope` for API calls
5.  Cancel coroutines when ViewModel is cleared
6.  Add retry policy with exponential backoff
7.  Handle connectivity state with `ConnectivityManager`

---

## Supported Platforms
✅ Android 8.0+ (API 26)
✅ JVM Desktop Applications
✅ Kotlin Multiplatform (JVM target)
✅ Ktor for multiplatform support (alternative)

All API endpoints are fully compatible with Kotlin and Android.