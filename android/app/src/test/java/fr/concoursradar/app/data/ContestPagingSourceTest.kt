package fr.concoursradar.app.data

import androidx.paging.PagingConfig
import androidx.paging.PagingSource
import androidx.paging.testing.TestPager
import fr.concoursradar.app.data.remote.AccountDto
import fr.concoursradar.app.data.remote.CategoryDto
import fr.concoursradar.app.data.remote.PostDto
import fr.concoursradar.app.data.remote.SupabaseApi
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ContestPagingSourceTest {

    private class FakeApi(private val total: Int) : SupabaseApi {
        val queries = mutableListOf<Map<String, String>>()
        override suspend fun posts(query: Map<String, String>): List<PostDto> {
            queries += query
            val offset = query.getValue("offset").toInt()
            val limit = query.getValue("limit").toInt()
            return (offset until minOf(total, offset + limit)).map { post("$it") }
        }
        override suspend fun categories() = emptyList<CategoryDto>()
        override suspend fun accounts() = emptyList<AccountDto>()
    }

    private val config = PagingConfig(pageSize = 20, initialLoadSize = 20, enablePlaceholders = false)
    private val today = LocalDate.of(2026, 11, 27)

    @Test
    fun `pages follow offsets and stop on a short page`() = runTest {
        val api = FakeApi(total = 30)
        val pager = TestPager(config, ContestPagingSource(api, FeedFilters(), today))
        val first = pager.refresh() as PagingSource.LoadResult.Page
        assertEquals(20, first.data.size)
        assertEquals(20, first.nextKey)
        val second = pager.append() as PagingSource.LoadResult.Page
        assertEquals(10, second.data.size)
        assertNull(second.nextKey)
        assertEquals(listOf("0", "20"), api.queries.map { it["offset"] })
    }

    @Test
    fun `missing configuration is an error, not a crash`() = runTest {
        val pager = TestPager(config, ContestPagingSource(FakeApi(5), FeedFilters(), today, configured = false))
        val result = pager.refresh()
        assertTrue(result is PagingSource.LoadResult.Error && result.throwable is MissingConfigException)
    }

    @Test
    fun `json row maps to a contest`() {
        val row = Json { ignoreUnknownKeys = true }.decodeFromString<PostDto>(
            """{"ig_media_id":"1","permalink":"https://www.instagram.com/p/x/","caption":" Concours ! ",
                "media_url":"https://cdn/x.mp4","media_type":"VIDEO","author_username":null,
                "published_at":"2026-11-27T11:20:00+00:00","categories":["livres"],
                "entry_type":"purchase","deadline":"2026-12-06","extra":1}""",
        )
        val contest = row.toContest()
        assertEquals("Concours !", contest.caption)
        assertNull(contest.imageUrl)                    // a video's media_url is an .mp4: not an image
        assertEquals(EntryType.PURCHASE, contest.entryType)
        assertEquals(LocalDate.of(2026, 12, 6), contest.deadline)
        assertEquals(1795778400000L, contest.publishedAt.toEpochMilli())
    }

    private fun post(id: String) = PostDto(
        id = id, permalink = "https://www.instagram.com/p/$id/", mediaType = "IMAGE",
        publishedAt = "2026-11-27T10:00:00+00:00",
    )
}
