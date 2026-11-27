package fr.concoursradar.app.data

import java.time.Instant
import java.time.LocalDate

/** How to enter, as computed by the collector (posts.entry_type). */
enum class EntryType(val dbValue: String) {
    INSTAGRAM("instagram"),
    PURCHASE("purchase"),
    IN_STORE("in_store"),
    EXTERNAL_FORM("external_form"),
    OTHER("other");

    companion object {
        fun fromDb(value: String?): EntryType = entries.firstOrNull { it.dbValue == value } ?: OTHER

        /** Offered as filters ("other" is not a useful filter). */
        val filterable = listOf(INSTAGRAM, PURCHASE, IN_STORE, EXTERNAL_FORM)
    }
}

enum class MediaType { IMAGE, VIDEO, CAROUSEL_ALBUM }

data class Contest(
    val id: String,
    val permalink: String,
    val caption: String,
    val imageUrl: String?,          // null for videos (media_url is an .mp4) or missing media
    val mediaType: MediaType,
    val author: String?,            // only for posts read from a followed account
    val publishedAt: Instant,
    val categories: List<String>,
    val entryType: EntryType,
    val deadline: LocalDate?,
)

data class Category(val slug: String, val label: String)

enum class SortOrder { RECENT, ENDING_SOON }

data class FeedFilters(
    val categories: Set<String> = emptySet(),
    val account: String? = null,
    val entryTypes: Set<EntryType> = emptySet(),
    val sort: SortOrder = SortOrder.RECENT,
) {
    val isFiltered: Boolean get() = categories.isNotEmpty() || account != null || entryTypes.isNotEmpty()
}
