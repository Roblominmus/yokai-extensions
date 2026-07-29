package eu.kanade.tachiyomi.util

import okhttp3.Response
import org.jsoup.Jsoup
import org.jsoup.nodes.Document

/** Parse a response body (or provided html) into a JSoup document with a base URI. */
fun Response.asJsoup(html: String? = null): Document =
    Jsoup.parse(html ?: body.string(), request.url.toString())
