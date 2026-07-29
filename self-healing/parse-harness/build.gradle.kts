// Plain Kotlin/JVM harness that runs a Tachiyomi/Keiyoushi extension source's
// parse methods against a live site — NO Android SDK required.
//
// How it works:
//   - src/main/kotlin/runtime/  -> a REAL implementation of the subset of the
//     `eu.kanade.tachiyomi.*` "extensions-lib" API that HTML sources use.
//     (The upstream lib is a compileOnly stub whose methods throw; we replace it.)
//   - src/main/kotlin/extension/ -> the target source's .kt files, copied in by
//     import_source.sh (so the harness stays self-contained and offline-buildable).
//   - Runner.kt instantiates the source, executes *Request() with a real OkHttp
//     client, calls *Parse(response), and asserts the result is non-empty.

plugins {
    kotlin("jvm") version "2.4.10"
    kotlin("plugin.serialization") version "2.4.10"
    application
}

repositories {
    mavenCentral()
    maven(url = "https://www.jitpack.io")
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:5.4.0")
    implementation("org.jsoup:jsoup:1.22.2")
    // jsoup 1.22's API carries org.jspecify @Nullable type-use annotations that the
    // Kotlin compiler must resolve (same reason the repo's version catalog needs it)
    implementation("org.jspecify:jspecify:1.0.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-protobuf:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.11.0")
    implementation("io.reactivex:rxjava:1.3.8")
}

application {
    mainClass.set("harness.RunnerKt")
}

kotlin {
    compilerOptions {
        // kotlin.time.Instant (used by some KeiSource sources) is opt-in on some toolchains
        freeCompilerArgs.addAll("-opt-in=kotlin.time.ExperimentalTime")
    }
}

// Compile with the JDK that runs Gradle (OpenJDK 21 here) instead of resolving a
// Gradle toolchain — avoids toolchain auto-provisioning which isn't configured.
tasks.named<JavaExec>("run") {
    // pass the target source id via: ./gradlew run --args="<sourceId>"
    // exit code is propagated so CI can gate on it
}
