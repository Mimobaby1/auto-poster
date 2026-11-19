# Einrichtung (einmalig, ca. 30–45 Minuten)

Logins, Passwörter und Keys machst du selbst. Keys kommen nie in den Chat, nur in GitHub-Secrets oder in die `.env`.

## 1. Instagram auf Profi-Konto
Insta-App → Einstellungen → Kontoart und Tools → **Zu professionellem Konto wechseln** (Creator oder Business; beides kostenlos).

## 2. Meta-App für deinen Instagram-Zugang
1. Auf https://developers.facebook.com mit deinem Facebook-Konto anmelden und als Entwickler registrieren.
2. **App erstellen**, Anwendungsfall **„Instagram-API“** wählen.
3. Unter **„API-Einrichtung mit Instagram-Login“** deinen Main-Insta hinzufügen. Falls verlangt: unter *App-Rollen → Instagram-Tester* einladen und die Einladung im Insta annehmen (Einstellungen → Apps und Websites).
4. **Token generieren**. Er gilt 60 Tage, die 21 Tage Kampagne müssen in diese Zeit fallen. Zusammen mit der Instagram-Konto-ID (`IG_USER_ID`) brauchst du ihn in Schritt 4.
5. Die App bleibt im **Entwicklungsmodus**. Für deinen eigenen Account ist keine Prüfung durch Meta nötig.

## 3. Buffer für die 3 TikTok-Accounts
1. Kostenloses Konto auf https://buffer.com anlegen.
2. Die 3 TikTok-Accounts als Kanäle verbinden. Buffer verlangt evtl. TikTok-Business-Konten (TikTok-App → Einstellungen → Konto → zu Business-Konto wechseln).
3. https://publish.buffer.com/settings/api → **API-Key erstellen**.

## 4. GitHub
1. Kostenloses Konto auf https://github.com.
2. Ich lege das Repo an und lade Code und Videos hoch, sobald du dich am Mac angemeldet hast.
3. Im Repo unter *Settings → Secrets and variables → Actions* drei Secrets eintragen: `IG_ACCESS_TOKEN`, `IG_USER_ID`, `BUFFER_API_KEY`.
4. *Settings → Pages* → Quelle „Deploy from a branch“, `main`, `/ (root)`. Damit sind die Videos unter einer öffentlichen Adresse erreichbar, die Instagram und Buffer zum Abholen brauchen. Die trage ich dann als `media_base_url` ein.

## 5. Prüfen, testen, starten
1. `pruefen`: Ich trage die Buffer-Kanal-IDs ein, dann muss alles grün sein.
2. `test-insta`: Testreel-Container wird angelegt, aber nicht gepostet.
3. `test-buffer tiktok_acc1`: wird eingeplant und sofort gelöscht.
4. In GitHub unter *Actions → poster → Run workflow* einmal mit „trocken“ laufen lassen.
5. Du nennst das Startdatum, ich setze `start JJJJ-MM-TT` und pushe. Ab dann läuft alles allein.
