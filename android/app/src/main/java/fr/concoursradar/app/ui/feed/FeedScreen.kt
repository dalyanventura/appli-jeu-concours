package fr.concoursradar.app.ui.feed

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.paging.LoadState
import androidx.paging.compose.LazyPagingItems
import androidx.paging.compose.collectAsLazyPagingItems
import androidx.paging.compose.itemKey
import fr.concoursradar.app.R
import fr.concoursradar.app.data.Contest
import fr.concoursradar.app.data.MissingConfigException
import fr.concoursradar.app.data.SortOrder
import java.time.Instant
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedScreen(viewModel: FeedViewModel = hiltViewModel()) {
    val filters by viewModel.filters.collectAsStateWithLifecycle()
    val options by viewModel.options.collectAsStateWithLifecycle()
    val contests = viewModel.contests.collectAsLazyPagingItems()
    val uriHandler = LocalUriHandler.current
    val listState = rememberLazyListState()
    var showAccounts by rememberSaveable { mutableStateOf(false) }
    val scrollBehavior = TopAppBarDefaults.enterAlwaysScrollBehavior()

    // back to the top whenever the filters change
    LaunchedEffect(filters) { listState.scrollToItem(0) }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.feed_title)) },
                actions = { SortMenu(filters.sort, viewModel::setSort) },
                scrollBehavior = scrollBehavior,
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            FilterBar(
                filters = filters,
                options = options,
                onAccountClick = { showAccounts = true },
                onClearAccount = { viewModel.setAccount(null) },
                onToggleEntryType = viewModel::toggleEntryType,
                onToggleCategory = viewModel::toggleCategory,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            PullToRefreshBox(
                isRefreshing = contests.loadState.refresh is LoadState.Loading && contests.itemCount > 0,
                onRefresh = {
                    contests.refresh()
                    if (options.categories.isEmpty()) viewModel.loadOptions()
                },
                modifier = Modifier.fillMaxSize(),
            ) {
                FeedList(
                    contests = contests,
                    options = options,
                    listState = listState,
                    filtered = filters.isFiltered,
                    onClearFilters = viewModel::clearFilters,
                    onRetry = {
                        contests.retry()
                        viewModel.loadOptions()
                    },
                    onOpen = { uriHandler.openUri(it) },
                )
            }
        }
    }

    if (showAccounts) {
        AccountSheet(
            accounts = options.accounts,
            selected = filters.account,
            onSelect = {
                viewModel.setAccount(it)
                showAccounts = false
            },
            onDismiss = { showAccounts = false },
        )
    }
}

@Composable
private fun FeedList(
    contests: LazyPagingItems<Contest>,
    options: FilterOptions,
    listState: LazyListState,
    filtered: Boolean,
    onClearFilters: () -> Unit,
    onRetry: () -> Unit,
    onOpen: (String) -> Unit,
) {
    val refresh = contests.loadState.refresh
    when {
        refresh is LoadState.Loading && contests.itemCount == 0 ->
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }

        refresh is LoadState.Error && contests.itemCount == 0 ->
            Message(
                title = stringResource(R.string.error_title),
                body = stringResource(
                    if (refresh.error is MissingConfigException) R.string.error_config else R.string.error_body,
                ),
                action = stringResource(R.string.retry),
                onAction = onRetry,
            )

        refresh is LoadState.NotLoading && contests.itemCount == 0 ->
            Message(
                title = stringResource(R.string.empty_title),
                action = if (filtered) stringResource(R.string.clear_filters) else null,
                onAction = onClearFilters,
            )

        else -> {
            val today = remember { LocalDate.now() }
            val now = remember(contests.itemCount) { Instant.now() }
            LazyColumn(
                state = listState,
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                items(count = contests.itemCount, key = contests.itemKey { it.id }) { index ->
                    contests[index]?.let { contest ->
                        ContestCard(contest, options, today, now, onOpen = { onOpen(contest.permalink) })
                    }
                }
                when (val append = contests.loadState.append) {
                    is LoadState.Loading -> item {
                        Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                    is LoadState.Error -> item {
                        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                            OutlinedButton(onClick = { contests.retry() }) { Text(stringResource(R.string.retry)) }
                        }
                    }
                    else -> Unit
                }
            }
        }
    }
}

@Composable
private fun Message(title: String, body: String? = null, action: String? = null, onAction: () -> Unit = {}) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        body?.let {
            Text(
                it,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
        action?.let { Button(onClick = onAction) { Text(it) } }
    }
}

@Composable
private fun SortMenu(current: SortOrder, onSelect: (SortOrder) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        TextButton(onClick = { open = true }) {
            Text(stringResource(if (current == SortOrder.RECENT) R.string.sort_recent else R.string.sort_ending_soon))
            Icon(Icons.Filled.ArrowDropDown, contentDescription = stringResource(R.string.sort_label))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            listOf(SortOrder.RECENT to R.string.sort_recent, SortOrder.ENDING_SOON to R.string.sort_ending_soon)
                .forEach { (sort, label) ->
                    DropdownMenuItem(
                        text = { Text(stringResource(label)) },
                        onClick = {
                            onSelect(sort)
                            open = false
                        },
                        trailingIcon = { if (sort == current) Icon(Icons.Filled.Check, contentDescription = null) },
                    )
                }
        }
    }
}
