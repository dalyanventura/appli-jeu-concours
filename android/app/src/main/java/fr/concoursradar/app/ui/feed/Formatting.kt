package fr.concoursradar.app.ui.feed

import androidx.annotation.StringRes
import fr.concoursradar.app.R
import fr.concoursradar.app.data.EntryType
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

sealed interface DeadlineLabel {
    data object Today : DeadlineLabel
    data object Tomorrow : DeadlineLabel
    data class On(val date: LocalDate) : DeadlineLabel
}

/** Null when there is no known deadline (or it has passed: the collector purges those). */
fun deadlineLabel(deadline: LocalDate?, today: LocalDate): DeadlineLabel? = when {
    deadline == null || deadline.isBefore(today) -> null
    deadline == today -> DeadlineLabel.Today
    deadline == today.plusDays(1) -> DeadlineLabel.Tomorrow
    else -> DeadlineLabel.On(deadline)
}

/** "6 déc." (same year) or "6 janv. 2027". */
fun shortDate(date: LocalDate, today: LocalDate, locale: Locale = Locale.FRANCE): String {
    val pattern = if (date.year == today.year) "d MMM" else "d MMM yyyy"
    return date.format(DateTimeFormatter.ofPattern(pattern, locale))
}

@StringRes
fun EntryType.labelRes(): Int = when (this) {
    EntryType.INSTAGRAM -> R.string.entry_instagram
    EntryType.PURCHASE -> R.string.entry_purchase
    EntryType.IN_STORE -> R.string.entry_in_store
    EntryType.EXTERNAL_FORM -> R.string.entry_external_form
    EntryType.OTHER -> R.string.entry_other
}

/** Placeholder thumbnail when there is no image (videos, expired or missing media_url). */
fun categoryEmoji(slug: String?): String = when (slug) {
    "mode_bijoux" -> "👗"
    "beaute_bien_etre" -> "💄"
    "jeux_video" -> "🎮"
    "jeux_societe" -> "🎲"
    "high_tech" -> "📱"
    "deco_maison" -> "🛋️"
    "bricolage" -> "🌿"
    "cinema_series" -> "🎬"
    "livres" -> "📚"
    "gastronomie" -> "🍫"
    "voyage" -> "✈️"
    "sorties_evenements" -> "🎟️"
    "sport" -> "⚽"
    "enfants_famille" -> "🧸"
    "animaux" -> "🐾"
    "bons_achat" -> "💶"
    else -> "🎁"
}
