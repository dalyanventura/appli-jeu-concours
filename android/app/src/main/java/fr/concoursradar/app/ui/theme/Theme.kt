package fr.concoursradar.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val Coral = Color(0xFFE8505B)

private val LightColors = lightColorScheme(
    primary = Coral,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFDAD8),
    onPrimaryContainer = Color(0xFF410006),
    secondaryContainer = Color(0xFFF6E1C3),
    onSecondaryContainer = Color(0xFF2A1800),
    background = Color(0xFFFFFBF8),
    surface = Color(0xFFFFFBF8),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFFFFB3B0),
    onPrimary = Color(0xFF680011),
    primaryContainer = Color(0xFF8F1A27),
    onPrimaryContainer = Color(0xFFFFDAD8),
    secondaryContainer = Color(0xFF5B4325),
    onSecondaryContainer = Color(0xFFF6E1C3),
    background = Color(0xFF1A1110),
    surface = Color(0xFF1A1110),
)

@Composable
fun ConcoursRadarTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val colors = when {
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S ->
            if (dark) dynamicDarkColorScheme(LocalContext.current) else dynamicLightColorScheme(LocalContext.current)
        dark -> DarkColors
        else -> LightColors
    }
    MaterialTheme(colorScheme = colors, content = content)
}
