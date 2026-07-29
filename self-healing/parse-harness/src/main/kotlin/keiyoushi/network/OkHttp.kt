package keiyoushi.network

import eu.kanade.tachiyomi.network.DEFAULT_CACHE_CONTROL
import eu.kanade.tachiyomi.network.DEFAULT_HEADERS
import eu.kanade.tachiyomi.network.GET
import eu.kanade.tachiyomi.network.await
import eu.kanade.tachiyomi.network.awaitSuccess
import okhttp3.CacheControl
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Response

/**
 * Suspend GET helpers used by KeiSource extensions as `client.get(url)`. The real
 * keiyoushi version uses context parameters to pull headers from the source; the
 * harness uses a default browser header set, which is sufficient to validate parsing.
 */
suspend fun OkHttpClient.get(
    url: HttpUrl,
    headers: Headers = DEFAULT_HEADERS,
    cacheControl: CacheControl = DEFAULT_CACHE_CONTROL,
    ensureSuccess: Boolean = true,
): Response {
    val call = newCall(GET(url, headers, cacheControl))
    return if (ensureSuccess) call.awaitSuccess() else call.await()
}

suspend fun OkHttpClient.get(
    url: String,
    headers: Headers = DEFAULT_HEADERS,
    cacheControl: CacheControl = DEFAULT_CACHE_CONTROL,
    ensureSuccess: Boolean = true,
): Response {
    val call = newCall(GET(url, headers, cacheControl))
    return if (ensureSuccess) call.awaitSuccess() else call.await()
}
