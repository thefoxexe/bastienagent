# Bastien Agent — Guide complet

## Ce que fait ce bot

Assistant IA personnel sur Telegram qui :
- Comprend le **langage naturel** en français
- Lit et crée des événements dans ton **Google Calendar**
- Gère tes **tâches** et **notes**
- Envoie un **briefing automatique** chaque matin à 7h30 (météo + agenda + tâches)

---

## Étape 1 — Connecter Google Calendar (depuis ton ordinateur)

Tu dois faire ça une seule fois depuis ta machine personnelle.

### Prérequis sur ton ordi
```bash
pip install google-auth-oauthlib python-dotenv
```

### Lancer le script d'autorisation
```bash
python gen_auth_url.py
```

Le script affiche une URL → ouvre-la dans ton navigateur → connecte-toi avec ton compte Google → autorise l'accès au calendrier.

Le navigateur va ensuite essayer d'aller sur `http://localhost` (ça va échouer) → **copie l'URL complète depuis la barre d'adresse** et colle-la dans le terminal.

Le script sauvegarde le token dans `google_token.json`.

### Récupérer le contenu du token
```bash
cat google_token.json
```

Copie tout le contenu JSON — tu en auras besoin à l'étape 3.

---

## Étape 2 — Déployer sur Railway (gratuit)

Railway est la façon la plus simple de faire tourner le bot 24h/24.

1. Va sur **railway.app** → crée un compte (gratuit)
2. Clique **New Project → Deploy from GitHub repo**
3. Connecte ton GitHub et sélectionne le repo `thefoxexe/bastienagent`
4. Railway détecte automatiquement le `Procfile` et lance le bot

---

## Étape 3 — Configurer les variables d'environnement sur Railway

Dans Railway → ton projet → **Variables**, ajoute :

| Variable | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Ton token BotFather |
| `TELEGRAM_USER_ID` | Ton ID Telegram |
| `ANTHROPIC_API_KEY` | Ta clé Anthropic |
| `OPENWEATHER_API_KEY` | Ta clé OpenWeatherMap |
| `CITY` | `Geneva` (ou ta ville) |
| `TIMEZONE` | `Europe/Zurich` |
| `BRIEFING_TIME` | `07:30` |
| `GOOGLE_TOKEN_JSON` | Le contenu complet de `google_token.json` (tout le JSON) |

---

## Utilisation

Parle naturellement à ton bot Telegram :

| Ce que tu dis | Ce qui se passe |
|---|---|
| "Qu'est-ce que j'ai aujourd'hui ?" | Affiche ton agenda |
| "Rdv dentiste mardi 10h" | Crée l'événement dans Google Calendar |
| "Ajoute acheter du pain à ma liste" | Crée une tâche |
| "Note : code wifi = abc123" | Sauvegarde une note |
| "Météo demain ?" | Affiche la météo de Genève |
| "Montre mes tâches" | Liste tes tâches en cours |
| "Marque la tâche 3 comme faite" | Complète la tâche #3 |

Commandes rapides :
- `/start` — message d'accueil + aide
- `/agenda` — agenda du jour
- `/taches` — tâches en cours
- `/notes` — tes notes récentes
- `/briefing` — briefing complet maintenant (sans attendre 7h30)
