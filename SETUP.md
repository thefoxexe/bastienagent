# Bastien Agent — Guide de déploiement

## Ce que fait ce bot

Assistant IA personnel sur Telegram :
- Comprend le langage naturel en français
- Lit et crée des événements Google Calendar
- Gère tes tâches et notes
- Envoie un briefing automatique chaque matin

---

## Étape 1 — Déployer sur Railway

1. Va sur **railway.app** → crée un compte gratuit
2. **New Project → Deploy from GitHub repo**
3. Connecte GitHub → sélectionne `thefoxexe/bastienagent`
4. Railway détecte le `Procfile` et lance le bot

---

## Étape 2 — Variables d'environnement sur Railway

Dans Railway → ton projet → **Variables**, ajoute :

| Variable | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `8699880802:AAF35LN4...` |
| `TELEGRAM_USER_ID` | `1421753924` |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
| `OPENWEATHER_API_KEY` | `b594981b5887f2f2...` |
| `CITY` | `Geneva` |
| `TIMEZONE` | `Europe/Zurich` |
| `BRIEFING_TIME` | `07:30` |
| `GOOGLE_CLIENT_ID` | `534121423593-t0vrb...` |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-ylhlqZm...` |

---

## Étape 3 — Récupérer l'URL publique de Railway

Une fois déployé, Railway donne une URL comme :
`bastienagent-production.up.railway.app`

---

## Étape 4 — Ajouter l'URL de callback Google

1. Va sur **console.cloud.google.com/apis/credentials**
2. Clique sur ton client OAuth → modifier (crayon)
3. Sous "URI de redirection autorisés", ajoute :
   `https://TON-URL.up.railway.app/oauth/callback`
4. Enregistrer

---

## Étape 5 — Connecter Google Calendar (1 clic)

1. Ouvre Telegram → ton bot
2. Envoie `/connecter_calendar`
3. Le bot t'envoie un bouton → clique dessus
4. Connecte-toi avec Google → autorise
5. Le bot te dit "✅ Google Calendar connecté !"

**C'est tout. Le bot tourne 24h/24.**
