package fr.concoursradar.app.data

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.PagingSource
import androidx.paging.PagingState
import fr.concoursradar.app.BuildConfig
import fr.concoursradar.app.data.remote.SupabaseApi
import kotlinx.coroutines.flow.Flow
import java.time.Clock
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

class MissingConfigException : IllegalStateException("SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY missing")

@Singleton
class ContestRepository @Inject constructor(
    private val api: SupabaseApi,
    private val clock: Clock,
) {
    val isConfigured: Boolean get() = BuildConfig.SUPABASE_URL.isNotBlank() && BuildConfig.SUPABASE_KEY.isNotBlank()

    fun contests(filters: FeedFilters): Flow<PagingData<Contest>> =
        Pager(PagingConfig(pageSize = PAGE_SIZE, enablePlaceholders = false)) {
            ContestPagingSource(api, filters, LocalDate.now(clock), isConfigured)
        }.flow

    suspend fun categories(): List<Category> {
        if (!isConfigured) throw MissingConfigException()
        return api.categories().map { it.toCategory() }
    }

    suspend fun accounts(): List<String> {
        if (!isConfigured) throw MissingConfigException()
        return api.accounts().map { it.username }
    }

    companion object {
        const val PAGE_SIZE = 20
    }
}

/** Offset-based pages: key = offset of the first row. */
class ContestPagingSource(
    private val api: SupabaseApi,
    private val filters: FeedFilters,
    private val today: LocalDate,
    private val configured: Boolean = true,
) : PagingSource<Int, Contest>() {

    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, Contest> {
        if (!configured) return LoadResult.Error(MissingConfigException())
        val offset = params.key ?: 0
        return try {
            val rows = api.posts(PostQuery.build(filters, today, params.loadSize, offset))
            LoadResult.Page(
                data = rows.map { it.toContest() },
                prevKey = null,                       // the feed only grows downwards
                nextKey = if (rows.size < params.loadSize) null else offset + rows.size,
            )
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            LoadResult.Error(e)
        }
    }

    override fun getRefreshKey(state: PagingState<Int, Contest>): Int? = null   // refresh from the top
}
