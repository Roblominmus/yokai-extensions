package eu.kanade.tachiyomi.source

import androidx.preference.PreferenceScreen
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import rx.Observable

interface Source {
    val id: Long
    val name: String
    fun fetchMangaDetails(manga: SManga): Observable<SManga>
    fun fetchChapterList(manga: SManga): Observable<List<SChapter>>
    fun fetchPageList(chapter: SChapter): Observable<List<Page>>
}

interface CatalogueSource : Source {
    val lang: String
    val supportsLatest: Boolean

    fun fetchPopularManga(page: Int): Observable<MangasPage>
    fun fetchSearchManga(page: Int, query: String, filters: FilterList): Observable<MangasPage>
    fun fetchLatestUpdates(page: Int): Observable<MangasPage>
    fun getFilterList(): FilterList

    val supportsRelatedMangas: Boolean get() = false
    val disableRelatedMangasBySearch: Boolean get() = false
    val disableRelatedMangas: Boolean get() = false
    suspend fun fetchRelatedMangaList(manga: SManga): List<SManga> =
        throw UnsupportedOperationException("Unsupported!")
}

interface ConfigurableSource {
    fun setupPreferenceScreen(screen: PreferenceScreen)
}
