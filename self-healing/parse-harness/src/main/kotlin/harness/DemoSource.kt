package harness

import eu.kanade.tachiyomi.network.GET
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.ParsedHttpSource
import okhttp3.Request
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

/**
 * A REAL ParsedHttpSource that scrapes mangapill.com's "recently released" page,
 * written against the exact same base classes a Keiyoushi extension uses. This is
 * the harness's built-in proof that the runtime executes a live request and parses
 * real HTML into models. Selectors verified against the live page:
 *   card = a[href^="/manga/"], title = div.font-bold inside it.
 */
open class DemoSource : ParsedHttpSource() {
    override val name = "MangapillDemo"
    override val lang = "en"
    override val baseUrl = "https://mangapill.com"
    override val supportsLatest = true

    // ---- Popular (the method the runner asserts on) ----
    override fun popularMangaRequest(page: Int): Request = GET("$baseUrl/chapters", headers)
    override fun popularMangaSelector(): String = "a[href^=\"/manga/\"]"
    override fun popularMangaFromElement(element: Element): SManga = SManga.create().apply {
        setUrlWithoutDomain(element.attr("href"))
        title = element.selectFirst("div.font-bold")?.text() ?: element.text()
    }
    override fun popularMangaNextPageSelector(): String? = null

    // ---- Search / Latest reuse the popular listing for this demo ----
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request =
        GET("$baseUrl/search?q=$query", headers)
    override fun searchMangaSelector(): String = popularMangaSelector()
    override fun searchMangaFromElement(element: Element): SManga = popularMangaFromElement(element)
    override fun searchMangaNextPageSelector(): String? = null

    override fun latestUpdatesRequest(page: Int): Request = GET("$baseUrl/chapters", headers)
    override fun latestUpdatesSelector(): String = popularMangaSelector()
    override fun latestUpdatesFromElement(element: Element): SManga = popularMangaFromElement(element)
    override fun latestUpdatesNextPageSelector(): String? = null

    // ---- Details / chapters / pages: minimal (not exercised by the popular check) ----
    override fun mangaDetailsParse(document: Document): SManga = SManga.create().apply {
        title = document.selectFirst("h1")?.text() ?: ""
    }
    override fun chapterListSelector(): String = "a[href^=\"/chapters/\"]"
    override fun chapterFromElement(element: Element): SChapter = SChapter.create().apply {
        setUrlWithoutDomain(element.attr("href"))
        name = element.text()
    }
    override fun pageListParse(document: Document): List<Page> =
        document.select("picture img").mapIndexed { i, img -> Page(i, "", img.attr("data-src")) }
    override fun imageUrlParse(document: Document): String = ""
}

/**
 * Same source, but with a STALE selector (as if mangapill changed its DOM and the
 * old `select("div.old-manga-card...")` no longer matches). Proves the validator
 * FAILS on breakage — this is the exact red signal that gates an AI repair.
 */
class DemoSourceBroken : DemoSource() {
    override val name = "MangapillDemo-STALE"
    override fun popularMangaSelector(): String = "div.old-manga-card > a.title"
}
