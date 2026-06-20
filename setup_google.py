"""
Script one-shot pour autoriser l'accès à Google Calendar.
Lance ce script une seule fois depuis ton ordinateur.
Il ouvrira un navigateur pour que tu te connectes à Google.
Le token est ensuite sauvé dans google_token.json.
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

CREDENTIALS_PATH = "google_credentials.json"

def main():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET manquants dans .env")
        print("\nSteps pour obtenir tes credentials :")
        print("1. Va sur https://console.cloud.google.com")
        print("2. Crée un projet ou sélectionnes-en un existant")
        print("3. Active l'API Google Calendar")
        print("4. Crée des identifiants OAuth 2.0 (type : Application de bureau)")
        print("5. Télécharge le fichier JSON et copie client_id et client_secret dans .env")
        return

    creds_data = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(creds_data, f)

    print("🔐 Lancement du flow OAuth Google Calendar...")
    from services.google_calendar import _get_service
    _get_service()
    print("✅ Authentification réussie ! Token sauvé dans google_token.json")
    print("Tu peux maintenant lancer le bot avec : python -m bot.main")


if __name__ == "__main__":
    main()
