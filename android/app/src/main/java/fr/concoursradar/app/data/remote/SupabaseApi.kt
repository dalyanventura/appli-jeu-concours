package fr.concoursradar.app.data.remote

import fr.concoursradar.app.data.Category
import fr.concoursradar.app.data.Contest
import fr.concoursradar.app.data.EntryType
import fr.concoursradar.app.data.MediaType
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.GET
import retrofit2.http.QueryMap
import java.time.LocalDate
import java.time.OffsetDateTime

/**
 * Supabase REST (PostgREST), read-only with the publishable key. RLS only exposes posts that look
 * like contests (contest_score >= 0.5, not hidden), the categories, and usernames of followed accounts.
 */
interface SupabaseApi {
    @GET("rest/v1/posts")
    suspend fun posts(@QueryMap query: Map<String, String>): List<PostDto>

    @GET("rest/v1/categories?select=slug,label&order=sort_order")
    suspend fun categories(): List<CategoryDto>

    @GET("rest/v1/accounts?select=username&order=username")
    suspend fun accounts(): List<AccountDto>
}

@Serializable
data class PostDto(
    @SerialName("ig_media_id") val id: String,
    val permalink: String,
    val caption: String? = null,
    @SerialName("media_url") val mediaUrl: String? = null,
    @SerialName("media_type") val mediaType: String,
    @SerialName("author_username") val author: String? = null,
    @SerialName("published_at") val publishedAt: String,
    val categories: List<String> = emptyList(),
    @SerialName("entry_type") val entryType: String? = null,
    val deadline: String? = null,
) {
    fun toContest(): Contest {
        val type = runCatching { MediaType.valueOf(mediaType) }.getOrDefault(MediaType.IMAGE)
        return Contest(
            id = id,
            permalink = permalink,
            caption = caption.orEmpty().trim(),
            imageUrl = mediaUrl.takeIf { type != MediaType.VIDEO },
            mediaType = type,
            author = author,
            publishedAt = OffsetDateTime.parse(publishedAt).toInstant(),
            categories = categories,
            entryType = EntryType.fromDb(entryType),
            deadline = deadline?.let(LocalDate::parse),
        )
    }
}

@Serializable
data class CategoryDto(val slug: String, val label: String) {
    fun toCategory() = Category(slug, label)
}

@Serializable
data class AccountDto(val username: String)
