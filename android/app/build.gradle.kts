import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

/**
 * Supabase URL + PUBLISHABLE key (never the secret key: it would ship inside the APK).
 * Looked up in android/local.properties (supabase.url / supabase.publishableKey), then in the
 * environment, then in the repository's .env (only these two names are read from it).
 */
fun supabaseSetting(propertyName: String, envName: String): String {
    val local = Properties().apply {
        rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
    }
    local.getProperty(propertyName)?.let { return it.trim() }
    System.getenv(envName)?.takeIf { it.isNotBlank() }?.let { return it.trim() }
    val dotEnv = rootProject.file("../.env")
    if (dotEnv.exists()) {
        dotEnv.readLines().map { it.trim() }
            .firstOrNull { it.startsWith("$envName=") }
            ?.substringAfter("=")?.trim()?.trim('"', '\'')
            ?.let { return it }
    }
    return ""
}

val supabaseUrl = supabaseSetting("supabase.url", "SUPABASE_URL")
val supabaseKey = supabaseSetting("supabase.publishableKey", "SUPABASE_PUBLISHABLE_KEY")
require(!supabaseKey.startsWith("sb_secret_")) { "La clé secrète Supabase ne doit jamais être mise dans l'app." }

android {
    namespace = "fr.concoursradar.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "fr.concoursradar.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "SUPABASE_URL", "\"$supabaseUrl\"")
        buildConfigField("String", "SUPABASE_KEY", "\"$supabaseKey\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false   // phase 7: enable R8 with serialization rules
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.core)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.paging.runtime)
    implementation(libs.paging.compose)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)

    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.paging.testing)
}
