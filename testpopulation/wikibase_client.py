import os
from pathlib import Path
import requests
from dotenv import dotenv_values


def load_config(env_file: str = None) -> dict:
    path = Path(env_file) if env_file else Path(__file__).parent / "../deploy/.env"
    values = dotenv_values(path)
    return {
        "base_url": f"https://{values['WIKIBASE_PUBLIC_HOST']}",
        "username": values["MW_ADMIN_NAME"],
        "password": values["MW_ADMIN_PASS"],
    }


class WikibaseClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/w/api.php"
        self.session = requests.Session()
        self.session.verify = False  # for local dev with self-signed/mkcert certs
        self._login(username, password)

    def _get_token(self, token_type: str = "login") -> str:
        response = self.session.get(self.api_url, params={
            "action": "query",
            "meta": "tokens",
            "type": token_type,
            "format": "json",
        })
        response.raise_for_status()
        return response.json()["query"]["tokens"][f"{token_type}token"]

    def _login(self, username: str, password: str) -> None:
        login_token = self._get_token("login")
        response = self.session.post(self.api_url, data={
            "action": "login",
            "lgname": username,
            "lgpassword": password,
            "lgtoken": login_token,
            "format": "json",
        })
        response.raise_for_status()
        result = response.json()["login"]
        if result["result"] != "Success":
            raise RuntimeError(f"Login failed: {result['reason']}")
        print(f"Logged in as {result['lgusername']}")

    def get_csrf_token(self) -> str:
        return self._get_token("csrf")


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    config = load_config()
    client = WikibaseClient(**config)
    token = client.get_csrf_token()
    print(f"CSRF token: {token[:20]}...")
    print("Connection successful.")
