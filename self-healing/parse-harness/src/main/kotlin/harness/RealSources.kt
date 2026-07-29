package harness

import eu.kanade.tachiyomi.extension.en.mangapill.MangaPill
import eu.kanade.tachiyomi.extension.en.weebcentral.WeebCentral

/**
 * Runnable wrapper for the UNMODIFIED MangaPill source imported from the repo.
 * The repo's `MangaPill` is `abstract` because @Source/KSP normally injects the
 * name/lang/baseUrl (and id) from the Gradle `source {}` DSL. We supply that same
 * metadata here so the source can be instantiated and validated. id is inherited
 * from HttpSource's computed default.
 */
class MangaPillRunnable : MangaPill() {
    override val name = "MangaPill"
    override val lang = "en"
    override val baseUrl = "https://mangapill.com"
}

/** Runnable wrapper for the unmodified WeebCentral source (KeiSource / suspend API). */
class WeebCentralRunnable : WeebCentral() {
    override val name = "Weeb Central"
    override val lang = "en"
    override val baseUrl = "https://weebcentral.com"
}
