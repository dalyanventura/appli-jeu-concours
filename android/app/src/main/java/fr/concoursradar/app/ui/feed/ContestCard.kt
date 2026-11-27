package fr.concoursradar.app.ui.feed

import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import fr.concoursradar.app.R
import fr.concoursradar.app.data.Contest
import fr.concoursradar.app.data.EntryType
import fr.concoursradar.app.data.MediaType
import java.time.Instant
import java.time.LocalDate

@Composable
fun ContestCard(
    contest: Contest,
    options: FilterOptions,
    today: LocalDate,
    now: Instant,
    onOpen: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        onClick = onOpen,
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Row(Modifier.padding(12.dp)) {
            Thumbnail(contest)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Header(contest, now)
                Text(
                    text = contest.caption,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 4,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 4.dp),
                )
                Badges(contest, options, today)
            }
        }
    }
}

@Composable
private fun Header(contest: Contest, now: Instant) {
    val published = DateUtils.getRelativeTimeSpanString(
        contest.publishedAt.toEpochMilli(), now.toEpochMilli(), DateUtils.MINUTE_IN_MILLIS,
    ).toString()
    Row(verticalAlignment = Alignment.CenterVertically) {
        contest.author?.let {
            Text(
                text = stringResource(R.string.by_account, it),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
            Text(" · ", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text(published, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun Thumbnail(contest: Contest) {
    val shape = RoundedCornerShape(12.dp)
    var failed by remember(contest.imageUrl) { mutableStateOf(contest.imageUrl == null) }
    Box(
        modifier = Modifier
            .size(92.dp)
            .clip(shape)
            .background(MaterialTheme.colorScheme.secondaryContainer),
        contentAlignment = Alignment.Center,
    ) {
        if (failed) {
            Text(categoryEmoji(contest.categories.firstOrNull()), style = MaterialTheme.typography.headlineLarge)
        } else {
            // media_url expires after a while (oe= parameter): fall back to the emoji on error
            AsyncImage(
                model = contest.imageUrl,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                onError = { failed = true },
                modifier = Modifier.fillMaxSize(),
            )
        }
        if (contest.mediaType == MediaType.VIDEO) {
            Surface(
                shape = RoundedCornerShape(50),
                color = Color.Black.copy(alpha = 0.55f),
                modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp),
            ) {
                Icon(
                    Icons.Filled.PlayArrow,
                    contentDescription = stringResource(R.string.video),
                    tint = Color.White,
                    modifier = Modifier.size(20.dp),
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Badges(contest: Contest, options: FilterOptions, today: LocalDate) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.padding(top = 8.dp),
    ) {
        when (val label = deadlineLabel(contest.deadline, today)) {
            DeadlineLabel.Today -> Badge(stringResource(R.string.deadline_today), urgent = true)
            DeadlineLabel.Tomorrow -> Badge(stringResource(R.string.deadline_tomorrow), urgent = true)
            is DeadlineLabel.On -> Badge(stringResource(R.string.deadline_on, shortDate(label.date, today)))
            null -> Unit
        }
        if (contest.entryType != EntryType.OTHER) {
            Badge(stringResource(contest.entryType.labelRes()))
        }
        contest.categories.filter { it != "autre" }.forEach { Badge(options.label(it), subtle = true) }
    }
}

@Composable
private fun Badge(text: String, urgent: Boolean = false, subtle: Boolean = false) {
    val colors = MaterialTheme.colorScheme
    val (container, content) = when {
        urgent -> colors.primary to colors.onPrimary
        subtle -> colors.surfaceContainerHighest to colors.onSurfaceVariant
        else -> colors.primaryContainer to colors.onPrimaryContainer
    }
    Surface(shape = RoundedCornerShape(8.dp), color = container, contentColor = content) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
        )
    }
}
