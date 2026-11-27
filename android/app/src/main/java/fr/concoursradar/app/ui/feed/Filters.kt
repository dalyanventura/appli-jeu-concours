package fr.concoursradar.app.ui.feed

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.InputChip
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import fr.concoursradar.app.R
import fr.concoursradar.app.data.EntryType
import fr.concoursradar.app.data.FeedFilters

private val rowPadding = PaddingValues(horizontal = 16.dp)
private val chipSpacing = Arrangement.spacedBy(8.dp)

/** Row 1: account + how to enter. Row 2: themes. */
@Composable
fun FilterBar(
    filters: FeedFilters,
    options: FilterOptions,
    onAccountClick: () -> Unit,
    onClearAccount: () -> Unit,
    onToggleEntryType: (EntryType) -> Unit,
    onToggleCategory: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        LazyRow(contentPadding = rowPadding, horizontalArrangement = chipSpacing) {
            item {
                val account = filters.account
                if (account == null) {
                    FilterChip(
                        selected = false,
                        onClick = onAccountClick,
                        label = { Text(stringResource(R.string.account_all)) },
                        leadingIcon = { Icon(Icons.Filled.Person, contentDescription = null) },
                        trailingIcon = { Icon(Icons.Filled.ArrowDropDown, contentDescription = null) },
                    )
                } else {
                    InputChip(
                        selected = true,
                        onClick = onAccountClick,
                        label = { Text(stringResource(R.string.account_filter, account)) },
                        trailingIcon = {
                            Icon(
                                Icons.Filled.Close,
                                contentDescription = stringResource(R.string.clear_filters),
                                modifier = Modifier.clickable(onClick = onClearAccount),
                            )
                        },
                    )
                }
            }
            items(EntryType.filterable) { type ->
                FilterChip(
                    selected = type in filters.entryTypes,
                    onClick = { onToggleEntryType(type) },
                    label = { Text(stringResource(type.labelRes())) },
                )
            }
        }
        LazyRow(contentPadding = rowPadding, horizontalArrangement = chipSpacing) {
            items(options.categories, key = { it.slug }) { category ->
                FilterChip(
                    selected = category.slug in filters.categories,
                    onClick = { onToggleCategory(category.slug) },
                    label = { Text("${categoryEmoji(category.slug)} ${category.label}") },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountSheet(
    accounts: List<String>,
    selected: String?,
    onSelect: (String?) -> Unit,
    onDismiss: () -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val visible = accounts.filter { query.isBlank() || it.contains(query.trim().removePrefix("@"), ignoreCase = true) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        Column(Modifier.navigationBarsPadding()) {
            Text(
                stringResource(R.string.account_sheet_title),
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 24.dp),
            )
            Text(
                stringResource(R.string.account_sheet_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
            )
            if (accounts.size > 8) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    singleLine = true,
                    label = { Text(stringResource(R.string.account_search)) },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp),
                )
            }
            LazyColumn {
                item {
                    AccountRow(stringResource(R.string.account_all), selected == null) { onSelect(null) }
                }
                items(visible, key = { it }) { username ->
                    AccountRow(stringResource(R.string.account_filter, username), selected == username) {
                        onSelect(username)
                    }
                }
                if (accounts.isEmpty()) {
                    item {
                        Text(
                            stringResource(R.string.account_none),
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(24.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AccountRow(text: String, checked: Boolean, onClick: () -> Unit) {
    ListItem(
        headlineContent = { Text(text) },
        trailingContent = { if (checked) Icon(Icons.Filled.Check, contentDescription = null) },
        modifier = Modifier.clickable(onClick = onClick).padding(horizontal = 8.dp),
    )
}
