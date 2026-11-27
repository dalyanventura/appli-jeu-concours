package fr.concoursradar.app.ui.feed

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import dagger.hilt.android.lifecycle.HiltViewModel
import fr.concoursradar.app.data.Category
import fr.concoursradar.app.data.Contest
import fr.concoursradar.app.data.ContestRepository
import fr.concoursradar.app.data.EntryType
import fr.concoursradar.app.data.FeedFilters
import fr.concoursradar.app.data.SortOrder
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class FilterOptions(
    val categories: List<Category> = emptyList(),
    val accounts: List<String> = emptyList(),
) {
    fun label(slug: String): String = categories.firstOrNull { it.slug == slug }?.label ?: slug
}

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class FeedViewModel @Inject constructor(private val repository: ContestRepository) : ViewModel() {

    private val _filters = MutableStateFlow(FeedFilters())
    val filters: StateFlow<FeedFilters> = _filters.asStateFlow()

    private val _options = MutableStateFlow(FilterOptions())
    val options: StateFlow<FilterOptions> = _options.asStateFlow()

    val isConfigured: Boolean get() = repository.isConfigured

    /** A new pager per filter change; cachedIn keeps pages across configuration changes. */
    val contests: Flow<PagingData<Contest>> = _filters
        .flatMapLatest { repository.contests(it) }
        .cachedIn(viewModelScope)

    init {
        loadOptions()
    }

    /** Themes and followed accounts; failures are silent here (the feed shows the error and retry). */
    fun loadOptions() {
        viewModelScope.launch {
            runCatching { repository.categories() }.onSuccess { list -> _options.update { it.copy(categories = list) } }
            runCatching { repository.accounts() }.onSuccess { list -> _options.update { it.copy(accounts = list) } }
        }
    }

    fun toggleCategory(slug: String) = _filters.update {
        it.copy(categories = if (slug in it.categories) it.categories - slug else it.categories + slug)
    }

    fun toggleEntryType(type: EntryType) = _filters.update {
        it.copy(entryTypes = if (type in it.entryTypes) it.entryTypes - type else it.entryTypes + type)
    }

    fun setAccount(username: String?) = _filters.update { it.copy(account = username) }

    fun setSort(sort: SortOrder) = _filters.update { it.copy(sort = sort) }

    fun clearFilters() = _filters.update { FeedFilters(sort = it.sort) }
}
