package keiyoushi.network

import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/**
 * No-op passthrough for the rate-limit builder extension. Real rate limiting is
 * irrelevant to a single validation request; we keep the signature so sources that
 * call `rateLimit(...)` in configureClient() compile and run unchanged.
 */
fun OkHttpClient.Builder.rateLimit(
    permits: Int,
    period: Duration = 1.seconds,
    interval: Duration = Duration.ZERO,
    shouldLimit: (HttpUrl) -> Boolean = { true },
): OkHttpClient.Builder = this
