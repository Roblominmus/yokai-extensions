package keiyoushi.source

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.model.SMangaUpdate
import eu.kanade.tachiyomi.source.online.HttpSource
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonElement
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import rx.Observable

/**
 * Real JVM implementation of Keiyoushi's newer suspend base class. Extensions
 * override the `getX` suspend methods; this base bridges them onto HttpSource's
 * RxJava `fetch*` API so the same runner (which calls `fetchPopularManga(...)`)
 * validates both classic and KeiSource sources. The legacy Request/Parse methods
 * are sealed off, exactly as upstream does.
 */
abstract class KeiSource : HttpSource() {

    override val supportsLatest: Boolean get() = true

    // ---- suspend API the extension implements ----
    abstract suspend fun getPopularManga(page: Int): MangasPage
    abstract suspend fun getLatestUpdates(page: Int): MangasPage
    abstract suspend fun getSearchMangaList(page: Int, query: String, filters: FilterList): MangasPage
    abstract suspend fun getPageList(chapter: SChapter): List<Page>
    abstract suspend fun fetchMangaUpdate(
        manga: SManga,
        chapters: List<SChapter>,
        fetchDetails: Boolean,
        fetchChapters: Boolean,
    ): SMangaUpdate

    open suspend fun getMangaByUrl(url: HttpUrl): SManga? = throw UnsupportedOperationException("getMangaByUrl not implemented")

    open fun getFilterList(data: JsonElement?): FilterList = FilterList()
    override fun getFilterList(): FilterList = getFilterList(null)

    open suspend fun getMangaUpdate(
        manga: SManga,
        chapters: List<SChapter>,
        fetchDetails: Boolean,
        fetchChapters: Boolean,
    ): SMangaUpdate = fetchMangaUpdate(manga, chapters, fetchDetails, fetchChapters).also {
        it.manga.initialized = true
    }

    // ---- client customization hook ----
    open fun OkHttpClient.Builder.configureClient(): OkHttpClient.Builder = this
    override val client: OkHttpClient by lazy { network.client.newBuilder().configureClient().build() }

    // ---- RxJava bridges onto the suspend API (what the runner calls) ----
    override fun fetchPopularManga(page: Int): Observable<MangasPage> =
        Observable.fromCallable { runBlocking { getPopularManga(page) } }
    override fun fetchLatestUpdates(page: Int): Observable<MangasPage> =
        Observable.fromCallable { runBlocking { getLatestUpdates(page) } }
    override fun fetchSearchManga(page: Int, query: String, filters: FilterList): Observable<MangasPage> =
        Observable.fromCallable { runBlocking { getSearchMangaList(page, query, filters) } }
    override fun fetchPageList(chapter: SChapter): Observable<List<Page>> =
        Observable.fromCallable { runBlocking { getPageList(chapter) } }
    override fun fetchMangaDetails(manga: SManga): Observable<SManga> =
        Observable.fromCallable { runBlocking { getMangaUpdate(manga, emptyList(), fetchDetails = true, fetchChapters = false).manga } }
    override fun fetchChapterList(manga: SManga): Observable<List<SChapter>> =
        Observable.fromCallable { runBlocking { getMangaUpdate(manga, emptyList(), fetchDetails = false, fetchChapters = true).chapters } }

    // ---- legacy request/parse API sealed off (KeiSource sources don't use it) ----
    override fun popularMangaRequest(page: Int): Request = throw UnsupportedOperationException()
    override fun popularMangaParse(response: Response): MangasPage = throw UnsupportedOperationException()
    override fun latestUpdatesRequest(page: Int): Request = throw UnsupportedOperationException()
    override fun latestUpdatesParse(response: Response): MangasPage = throw UnsupportedOperationException()
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request = throw UnsupportedOperationException()
    override fun searchMangaParse(response: Response): MangasPage = throw UnsupportedOperationException()
    override fun mangaDetailsParse(response: Response): SManga = throw UnsupportedOperationException()
    override fun chapterListParse(response: Response): List<SChapter> = throw UnsupportedOperationException()
    override fun pageListParse(response: Response): List<Page> = throw UnsupportedOperationException()
    override fun imageUrlParse(response: Response): String = throw UnsupportedOperationException()
}
