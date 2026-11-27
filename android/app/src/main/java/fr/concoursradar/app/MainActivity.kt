package fr.concoursradar.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import dagger.hilt.android.AndroidEntryPoint
import fr.concoursradar.app.ui.feed.FeedScreen
import fr.concoursradar.app.ui.theme.ConcoursRadarTheme

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ConcoursRadarTheme {
                FeedScreen()
            }
        }
    }
}
