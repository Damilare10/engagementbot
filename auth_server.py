# auth_server.py

from flask import Flask, redirect, request, session
import requests
import secrets
import base64
import hashlib
import sqlite3
import base64

app = Flask(__name__)
app.secret_key = '2Uv1UEFPgo8ow0pFVLffpGWOsGpB0YZKESOTi9itMIJq9a5F7e'

CLIENT_ID = "dUtBWEVpSC1IX20zZFROOFJiUG06MTpjaQ"
REDIRECT_URI = "https://engagementbot-production.up.railway.app/callback"
DB_PATH = 'twitter_accounts.db'


def generate_pkce_pair():
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


@app.route("/")
def home():
    return "✅ Twitter Auth Server Running. Visit /login to start."


@app.route("/login")
def login():
    session["code_verifier"], code_challenge = generate_pkce_pair()
    session["state"] = secrets.token_urlsafe(16)
    return redirect(
        f"https://x.com/i/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=users.read tweet.read like.write offline.access"
        f"&state={session['state']}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if not code or state != session.get("state"):
        return "Missing code or invalid state", 400

    basic_auth = base64.b64encode(f"{CLIENT_ID}:".encode()).decode()

    # Exchange code for tokens
    token_res = requests.post("https://api.twitter.com/2/oauth2/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": session["code_verifier"]
    }, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic_auth}"
    })
    token_data = token_res.json()
    print("🔑 Token data:", token_data)

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        return f"❌ Access token missing. Full response: {token_data}", 400

    # Get user info
    user_res = requests.get(
        "https://api.twitter.com/2/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    try:
        user_data = user_res.json()
        print("👤 Raw user data:", user_data)

        user_info = user_data.get("data")
        if not user_info:
            return f"❌ User data not found: {user_data}", 400

        twitter_id = user_info.get("id")
        twitter_handle = user_info.get("username")

        if not twitter_handle or not twitter_id:
            return f"❌ Twitter ID or handle missing in: {user_data}", 400

    except Exception as e:
        return f"❌ Error parsing user data: {str(e)}", 500

    # Save tokens to DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO twitter_accounts
        (twitter_id, twitter_handle, access_token, refresh_token, token_expiry)
        VALUES (?, ?, ?, ?, datetime('now', ? || ' seconds'))
    """, (twitter_id, twitter_handle, access_token, refresh_token, expires_in))
    conn.commit()
    conn.close()

    return f"✅ Connected Twitter account @{twitter_handle} successfully!"


# Run the Flask server
if __name__ == "__main__":
    app.run(debug=True)
