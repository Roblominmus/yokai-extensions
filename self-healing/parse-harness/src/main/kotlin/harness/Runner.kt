package harness

import eu.kanade.tachiyomi.network.NetworkHelper
import eu.kanade.tachiyomi.source.CatalogueSource
import okhttp3.OkHttpClient
import uy.kohesive.injekt.Injekt
import java.util.concurrent.TimeUnit
import kotlin.system.exitProcess

/**
 * Authoritative parse validator. Instantiates a real source, executes its
 * *Request() with a live OkHttp client, runs *Parse(), and asserts the result is
 * non-empty & well-shaped. Exit code: 0 = all checks passed, 1 = a parse produced
 * nothing (the source is broken), 2 = usage error. CI gates on this.
 */

private val sources: Map<String, () -> CatalogueSource> = mapOf(
    "demo" to { DemoSource() },
    "demo-broken" to { DemoSourceBroken() },
    // real repo sources, imported unmodified via import_source.sh:
    "mangapill" to { MangaPillRunnable() },
    "weebcentral" to { WeebCentralRunnable() },
)

private fun setupInjekt() {
    val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    Injekt.addSingleton(NetworkHelper(client))
}

private fun assertNonEmpty(label: String, items: List<String>) {
    val nonBlank = items.filter { it.isNotBlank() }
    if (nonBlank.isEmpty()) {
        throw AssertionError("$label produced 0 non-empty items (parse failed / layout changed)")
    }
}

private fun runCheck(name: String, block: () -> List<String>): Int {
    return try {
        val items = block()
        val nonBlank = items.count { it.isNotBlank() }
        val sample = items.filter { it.isNotBlank() }.take(3).joinToString(" | ")
        println("  PASS  %-8s %d items   e.g. %s".format(name, nonBlank, sample))
        0
    } catch (e: Throwable) {
        println("  FAIL  %-8s %s".format(name, e.message ?: e.toString()))
        1
    }
}

fun main(args: Array<String>) {
    val id = args.getOrNull(0) ?: "demo"
    setupInjekt()

    val factory = sources[id]
    if (factory == null) {
        println("unknown source '$id'. known: ${sources.keys.joinToString()}")
        exitProcess(2)
    }
    val source = factory()

    println("== parse-harness ==")
    println("source: ${source.name} (${source.lang})  id=${source.id}")
    println("running live parse checks...")

    var failures = 0

    failures += runCheck("popular") {
        val page = source.fetchPopularManga(1).toBlocking().first()
        assertNonEmpty("popular.mangas", page.mangas.map { it.title })
        // also assert urls are populated (a common half-broken-selector symptom)
        assertNonEmpty("popular.urls", page.mangas.map { it.url })
        page.mangas.map { it.title }
    }

    if (source.supportsLatest) {
        failures += runCheck("latest") {
            val page = source.fetchLatestUpdates(1).toBlocking().first()
            assertNonEmpty("latest.mangas", page.mangas.map { it.title })
            page.mangas.map { it.title }
        }
    }

    println("-".repeat(50))
    if (failures == 0) {
        println("RESULT: PASS — source parses live data correctly")
        exitProcess(0)
    } else {
        println("RESULT: FAIL — $failures check(s) produced no data")
        exitProcess(1)
    }
}
