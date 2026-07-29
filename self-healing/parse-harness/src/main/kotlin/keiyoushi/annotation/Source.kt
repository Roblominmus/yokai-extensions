package keiyoushi.annotation

/**
 * No-op stand-in for the @Source marker. In the real repo a KSP processor reads it
 * and generates a subclass supplying name/lang/id/baseUrl from the Gradle `source {}`
 * DSL. SOURCE retention → never in bytecode; the harness supplies that metadata via a
 * small runnable subclass instead (see harness/RealSources.kt).
 */
@Retention(AnnotationRetention.SOURCE)
@Target(AnnotationTarget.CLASS)
annotation class Source
