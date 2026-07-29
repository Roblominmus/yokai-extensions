package eu.kanade.tachiyomi.network

import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.CacheControl
import okhttp3.Callback
import okhttp3.FormBody
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import rx.Observable
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

const val DEFAULT_UA =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

val DEFAULT_HEADERS: Headers = Headers.Builder().add("User-Agent", DEFAULT_UA).build()
val DEFAULT_CACHE_CONTROL: CacheControl = CacheControl.Builder().build()
val DEFAULT_BODY: RequestBody = FormBody.Builder().build()

val jsonInstance = Json {
    ignoreUnknownKeys = true
    isLenient = true
    explicitNulls = false
}

fun GET(url: String, headers: Headers = DEFAULT_HEADERS, cache: CacheControl = DEFAULT_CACHE_CONTROL): Request =
    Request.Builder().url(url).headers(headers).cacheControl(cache).build()

fun GET(url: HttpUrl, headers: Headers = DEFAULT_HEADERS, cache: CacheControl = DEFAULT_CACHE_CONTROL): Request =
    Request.Builder().url(url).headers(headers).cacheControl(cache).build()

fun POST(
    url: String,
    headers: Headers = DEFAULT_HEADERS,
    body: RequestBody = DEFAULT_BODY,
    cache: CacheControl = DEFAULT_CACHE_CONTROL,
): Request = Request.Builder().url(url).post(body).headers(headers).cacheControl(cache).build()

/** Stand-in for the app's NetworkHelper: wraps a real OkHttpClient. Context ignored. */
class NetworkHelper(val client: OkHttpClient) {
    val cloudflareClient: OkHttpClient get() = client
    fun defaultUserAgentProvider(): String = DEFAULT_UA
}

fun Call.asObservable(): Observable<Response> = Observable.fromCallable { execute() }

fun Call.asObservableSuccess(): Observable<Response> = asObservable().map { response ->
    if (!response.isSuccessful) {
        response.close()
        throw Exception("HTTP error ${response.code}")
    }
    response
}

suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) = cont.resume(response)
        override fun onFailure(call: Call, e: IOException) {
            if (!cont.isCancelled) cont.resumeWithException(e)
        }
    })
    cont.invokeOnCancellation { runCatching { cancel() } }
}

suspend fun Call.awaitSuccess(): Response {
    val response = await()
    if (!response.isSuccessful) {
        response.close()
        throw Exception("HTTP error ${response.code}")
    }
    return response
}

inline fun <reified T> Response.parseAs(): T = use {
    jsonInstance.decodeFromString(body.string())
}
