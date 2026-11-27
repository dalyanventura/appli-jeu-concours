package fr.concoursradar.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import java.time.LocalDate

class PostQueryTest {
    private val today = LocalDate.of(2026, 11, 27)

    @Test
    fun `default query hides expired contests and sorts by date`() {
        val q = PostQuery.build(FeedFilters(), today, limit = 20, offset = 40)
        assertEquals("(deadline.is.null,deadline.gte.2026-11-27)", q["or"])
        assertEquals("published_at.desc,ig_media_id.desc", q["order"])
        assertEquals("20", q["limit"])
        assertEquals("40", q["offset"])
        assertFalse("categories" in q || "author_username" in q || "entry_type" in q)
    }

    @Test
    fun `filters are translated to PostgREST operators`() {
        val filters = FeedFilters(
            categories = setOf("livres", "beaute_bien_etre"),
            account = "marque_exemple",
            entryTypes = setOf(EntryType.PURCHASE, EntryType.INSTAGRAM),
            sort = SortOrder.ENDING_SOON,
        )
        val q = PostQuery.build(filters, today, 20, 0)
        assertEquals("ov.{beaute_bien_etre,livres}", q["categories"])
        assertEquals("eq.marque_exemple", q["author_username"])
        assertEquals("in.(instagram,purchase)", q["entry_type"])
        assertEquals("deadline.asc.nullslast,published_at.desc,ig_media_id.desc", q["order"])
    }

    @Test
    fun `selected columns never include moderation or scoring fields`() {
        assertFalse("is_hidden" in PostQuery.COLUMNS || "contest_score" in PostQuery.COLUMNS)
    }
}
