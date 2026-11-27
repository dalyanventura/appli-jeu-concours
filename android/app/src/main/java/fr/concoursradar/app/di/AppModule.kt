package fr.concoursradar.app.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import fr.concoursradar.app.BuildConfig
import fr.concoursradar.app.data.remote.SupabaseApi
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.time.Clock
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun okHttp(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val key = BuildConfig.SUPABASE_KEY
            val request = chain.request().newBuilder().header("apikey", key).apply {
                if (key.startsWith("eyJ")) header("Authorization", "Bearer $key")   // legacy anon JWT
            }.build()
            chain.proceed(request)
        }
        .build()

    @Provides
    @Singleton
    fun api(client: OkHttpClient): SupabaseApi {
        val json = Json { ignoreUnknownKeys = true }
        val baseUrl = BuildConfig.SUPABASE_URL.trimEnd('/').ifBlank { "https://not-configured.invalid" } + "/"
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(SupabaseApi::class.java)
    }

    @Provides
    fun clock(): Clock = Clock.systemDefaultZone()
}
