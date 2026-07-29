package eu.kanade.tachiyomi.source.model

/** Result holder returned by KeiSource.fetchMangaUpdate (extensions-lib 1.6). */
class SMangaUpdate(val manga: SManga, val chapters: List<SChapter>)
