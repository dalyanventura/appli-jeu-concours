# Concours Radar — app Android

Lit les concours dans Supabase (lecture seule, clé **publique**) et ouvre la publication Instagram d'origine.

## Configuration

L'app a besoin de `SUPABASE_URL` et de `SUPABASE_PUBLISHABLE_KEY`, cherchés dans cet ordre :

1. `android/local.properties` : `supabase.url=…` et `supabase.publishableKey=…` ;
2. les variables d'environnement `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` (CI GitHub) ;
3. le `.env` à la racine du dépôt (seules ces deux lignes sont lues).

**Jamais la clé secrète** (`sb_secret_…`) : elle serait lisible dans l'APK. Le build refuse une clé `sb_secret_`.

## Commandes (Windows : `gradlew.bat`)

```bash
./gradlew assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew testDebugUnitTest    # tests unitaires
./gradlew installDebug         # sur un téléphone branché (débogage USB) ou un émulateur
```

Sans Android Studio : chaque push lance le workflow **Tests**, qui publie l'APK de debug dans
*Actions → Tests → (dernier run) → Artifacts → concours-radar-debug-apk*.
