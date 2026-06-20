"""Génère l'URL d'autorisation Google et attend le code de retour."""
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

CREDENTIALS_PATH = "google_credentials.json"
TOKEN_PATH = "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_PATH,
        scopes=SCOPES,
        redirect_uri="http://localhost",
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    print("\n" + "="*60)
    print("ÉTAPE 1 — Ouvre cette URL dans ton navigateur :")
    print("="*60)
    print(f"\n{auth_url}\n")
    print("="*60)
    print("ÉTAPE 2 — Après avoir autorisé l'accès :")
    print("  Le navigateur essaiera d'aller sur localhost (ça va échouer)")
    print("  Copie l'URL COMPLÈTE depuis la barre d'adresse")
    print("  Elle ressemble à : http://localhost/?code=4/0A...&scope=...")
    print("="*60)

    if len(sys.argv) > 1:
        redirect_url = sys.argv[1]
    else:
        redirect_url = input("\nColle l'URL ici et appuie sur Entrée :\n> ").strip()

    flow.fetch_token(authorization_response=redirect_url)
    creds = flow.credentials

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }

    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✅ Token sauvé dans {TOKEN_PATH}")
    print("Google Calendar est maintenant connecté !")


if __name__ == "__main__":
    main()
