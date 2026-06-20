# Bastien Agent — Guide de démarrage

## Ce que fait ce bot

Un assistant IA personnel sur Telegram qui :
- Lit et crée des événements dans ton **Google Calendar**
- Gère tes **tâches** et **notes**
- Envoie un **briefing automatique** chaque matin (météo + agenda + tâches)
- Comprend le **langage naturel** en français

---

## Installation (5 étapes)

### 1. Prérequis
- Python 3.11+
- Un compte Telegram
- Un compte Google (pour Calendar)
- Clés API : Anthropic + OpenWeatherMap (gratuit)

### 2. Cloner et installer

```bash
git clone https://github.com/thefoxexe/bastienagent
cd bastienagent
pip install -r requirements.txt
```

### 3. Créer le fichier `.env`

Copie `.env.example` en `.env` et remplis :

```bash
cp .env.example .env
```

#### Obtenir le token Telegram :
1. Ouvre Telegram → cherche **@BotFather**
2. Envoie `/newbot` → suis les instructions
3. Copie le token dans `TELEGRAM_BOT_TOKEN`

#### Obtenir ton Telegram User ID :
1. Cherche **@userinfobot** sur Telegram
2. Envoie `/start` → il affiche ton ID
3. Copie-le dans `TELEGRAM_USER_ID`

#### Clé Anthropic (Claude AI) :
- Va sur https://console.anthropic.com → API Keys
- Copie dans `ANTHROPIC_API_KEY`

#### Clé OpenWeatherMap (météo, gratuit) :
- Crée un compte sur https://openweathermap.org/api
- Copie la clé gratuite dans `OPENWEATHER_API_KEY`

### 4. Connecter Google Calendar

```bash
python setup_google.py
```

Cela ouvre ton navigateur → connecte-toi avec ton compte Google → autorise l'accès.

### 5. Lancer le bot

```bash
python -m bot.main
```

---

## Utilisation

Parle naturellement à ton bot Telegram :

| Ce que tu dis | Ce qui se passe |
|---|---|
| "Qu'est-ce que j'ai aujourd'hui ?" | Affiche ton agenda |
| "Rdv dentiste mardi 10h" | Crée l'événement |
| "Ajoute acheter du pain à ma liste" | Crée une tâche |
| "Note : code wifi = abc123" | Sauve une note |
| "Météo demain ?" | Affiche la météo |
| "Montre mes tâches" | Liste tes tâches |

Commandes rapides :
- `/agenda` — agenda du jour
- `/taches` — tâches en cours  
- `/notes` — tes notes
- `/briefing` — briefing complet maintenant

Le briefing automatique arrive chaque matin à l'heure configurée dans `.env`.

---

## Déploiement (pour que le bot tourne en permanence)

Options recommandées :
- **Railway** (gratuit jusqu'à 5$/mois de crédit) — le plus simple
- **Render** (free tier disponible)
- **VPS** (DigitalOcean, Hetzner, etc.)

Sur Railway : connecte le repo GitHub → configure les variables d'env → deploy.
