package fr.concoursradar.app.data

import java.time.LocalDate

/** PostgREST query parameters for one page of the feed. */
object PostQuery {
    const val COLUMNS = "ig_media_id,permalink,caption,media_url,media_type,author_username," +
        "published_at,categories,entry_type,deadline"

    fun build(filters: FeedFilters, today: LocalDate, limit: Int, offset: Int): Map<String, String> = buildMap {
        put("select", COLUMNS)
        // the collector purges expired contests hourly; this also hides those of the current hour
        put("or", "(deadline.is.null,deadline.gte.$today)")
        if (filters.categories.isNotEmpty()) {
            put("categories", "ov.{${filters.categories.sorted().joinToString(",")}}")   // any of
        }
        filters.account?.let { put("author_username", "eq.$it") }
        if (filters.entryTypes.isNotEmpty()) {
            put("entry_type", "in.(${filters.entryTypes.map { it.dbValue }.sorted().joinToString(",")})")
        }
        // ig_media_id breaks ties so that offset pages never overlap
        put("order", when (filters.sort) {
            SortOrder.RECENT -> "published_at.desc,ig_media_id.desc"
            SortOrder.ENDING_SOON -> "deadline.asc.nullslast,published_at.desc,ig_media_id.desc"
        })
        put("limit", limit.toString())
        put("offset", offset.toString())
    }
}
