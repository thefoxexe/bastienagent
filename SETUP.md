# Bastien Agent — Déploiement gratuit sur Render

## Étape 1 — Déployer sur Render (gratuit)

1. Va sur **render.com** → crée un compte gratuit
2. **New → Web Service**
3. Connecte GitHub → sélectionne `thefoxexe/bastienagent`
4. Configure :
   - **Name** : `bastienagent`
   - **Branch** : `claude/personalized-ai-agent-7gvqw3`
   - **Runtime** : `Python 3`
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `python -m bot.main`
   - **Plan** : `Free`
5. Clique **Create Web Service**

---

## Étape 2 — Variables d'environnement sur Render

Dans Render → ton service → **Environment** → ajoute :

| Variable | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | ton token |
| `TELEGRAM_USER_ID` | `1421753924` |
| `ANTHROPIC_API_KEY` | ta clé |
| `OPENWEATHER_API_KEY` | ta clé météo |
| `CITY` | `Geneva` |
| `TIMEZONE` | `Europe/Zurich` |
| `BRIEFING_TIME` | `07:30` |
| `GOOGLE_CLIENT_ID` | ton client ID Google |
| `GOOGLE_CLIENT_SECRET` | ton secret Google |
| `CRON_SECRET` | un mot de passe de ton choix (ex: `bastien2024`) |

---

## Étape 3 — Récupérer ton URL Render

Après le deploy, Render donne une URL comme :
`https://bastienagent.onrender.com`

---

## Étape 4 — Ajouter l'URL de callback dans Google Cloud

1. **console.cloud.google.com/apis/credentials**
2. Clique sur ton client OAuth → modifier
3. "URI de redirection autorisés" → ajoute :
   `https://bastienagent.onrender.com/oauth/callback`
4. Enregistrer

---

## Étape 5 — Connecter Google Calendar (1 clic depuis Telegram)

Dans Telegram, envoie `/connecter_calendar` → clique le bouton → autorise → c'est fait.

---

## Étape 6 — Briefing automatique gratuit (cron-job.org)

Pour que le briefing arrive chaque matin même si l'app dort :

1. Va sur **cron-job.org** → crée un compte gratuit
2. **Create cronjob** :
   - URL : `https://bastienagent.onrender.com/cron/briefing?secret=bastien2024`
   - Schedule : `30 7 * * *` (chaque jour à 7h30)
3. Save
