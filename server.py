# server.py
import os
import sqlite3
import time
import random
import requests
import secrets
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Flask, redirect, request, session, render_template

# ─────────────────────────────────────────────────────────────
# Configuration & Constants
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "SyMW4s9ipYVJEWL5nBOlPPQzRSMlBmLjbWZb78OXSNnq96d1Cm"

CLIENT_ID = "dUtBWEVpSC1IX20zZFROOFJiUG06MTpjaQ"  # 🔒 Your real Client ID here
REDIRECT_URI = os.getenv(
    "REDIRECT_URI",  "https://engagementbot-production.up.railway.app/callback")
DB_PATH = os.getenv("DB_PATH",       "twitter_accounts.db")
PORT = int(os.getenv("PORT",      5000))

# ─────────────────────────────────────────────────────────────
# Database Setup (runs on every start)
# ─────────────────────────────────────────────────────────────


def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Accounts table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS twitter_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        twitter_id TEXT UNIQUE,
        twitter_handle TEXT,
        access_token TEXT,
        refresh_token TEXT,
        token_expiry DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    # Settings table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    # Initialize keys if missing
    cur.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('tweet_id','')")
    cur.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('follow_target_id','')")
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────
# PKCE Helpers
# ─────────────────────────────────────────────────────────────


def generate_pkce_pair():
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge

# ─────────────────────────────────────────────────────────────
# Token Refresh Helper
# ─────────────────────────────────────────────────────────────


def refresh_token_if_expired(cursor, twitter_id, access_token, refresh_token, expiry_str):
    expiry = datetime.fromisoformat(expiry_str)
    if expiry > datetime.now(timezone.utc):
        return access_token

    res = requests.post("https://api.twitter.com/2/oauth2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if res.status_code != 200:
        return None

    data = res.json()
    new_access = data["access_token"]
    new_refresh = data["refresh_token"]
    new_expiry = (datetime.now(timezone.utc) +
                  timedelta(seconds=data["expires_in"])).isoformat()

    cursor.execute("""
      UPDATE twitter_accounts
      SET access_token=?, refresh_token=?, token_expiry=?
      WHERE twitter_id=?
    """, (new_access, new_refresh, new_expiry, twitter_id))
    return new_access

# ─────────────────────────────────────────────────────────────
# Like & Follow Logic
# ─────────────────────────────────────────────────────────────


def like_from_accounts(tweet_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT twitter_id, twitter_handle, access_token, refresh_token, token_expiry FROM twitter_accounts")
    results = []
    for tid, handle, token, refresh, expiry in cur.fetchall():
        token = refresh_token_if_expired(cur, tid, token, refresh, expiry)
        if not token:
            results.append((handle, "❌ Token Refresh Failed"))
        else:
            r = requests.post(
                f"https://api.twitter.com/2/users/{tid}/likes",
                headers={"Authorization": f"Bearer {token}"},
                json={"tweet_id": tweet_id}
            )
            if r.status_code == 201:
                status = "✅ Liked"
            elif r.status_code == 200 and '"liked":true' in r.text:
                status = "✅ Already Liked"
            else:
                status = f"❌ {r.status_code}: {r.text}"
            results.append((handle, status))
        time.sleep(random.uniform(1.5, 3.0))
    conn.commit()
    conn.close()
    return results


def follow_from_accounts(target_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT twitter_id, twitter_handle, access_token, refresh_token, token_expiry FROM twitter_accounts")
    results = []
    for tid, handle, token, refresh, expiry in cur.fetchall():
        token = refresh_token_if_expired(cur, tid, token, refresh, expiry)
        if not token:
            results.append((handle, "❌ Token Refresh Failed"))
        else:
            r = requests.post(
                f"https://api.twitter.com/2/users/{tid}/following",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": target_id}
            )
            if r.status_code == 201:
                status = "✅ Followed"
            elif r.status_code == 200 and '"following":true' in r.text:
                status = "✅ Already Following"
            else:
                status = f"❌ {r.status_code}: {r.text}"
            results.append((handle, status))
        time.sleep(random.uniform(1.5, 3.0))
    conn.commit()
    conn.close()
    return results

# ─────────────────────────────────────────────────────────────
# Settings Helpers
# ─────────────────────────────────────────────────────────────


def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""


def set_setting(key, val):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────
# Routes: OAuth
# ─────────────────────────────────────────────────────────────


@app.route("/login")
def login():
    session["code_verifier"], challenge = generate_pkce_pair()
    session["state"] = secrets.token_urlsafe(16)
    return redirect(
        "https://twitter.com/i/oauth2/authorize"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=users.read tweet.read like.write offline.access"
        f"&state={session['state']}"
        f"&code_challenge={challenge}"
        "&code_challenge_method=S256"
    )


@app.route("/callback")
def callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or state != session.get("state"):
        return "❌ Code/state mismatch", 400

    # exchange
    tok = requests.post("https://api.twitter.com/2/oauth2/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": session["code_verifier"]
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}).json()

    if not tok.get("access_token"):
        return f"❌ Token error: {tok}", 400

    at = tok["access_token"]
    rt = tok["refresh_token"]
    exp = (datetime.now(timezone.utc) +
           timedelta(seconds=tok["expires_in"])).isoformat()

    # get user
    user = requests.get(
        "https://api.twitter.com/2/users/me",
        headers={"Authorization": f"Bearer {at}"}
    ).json().get("data", {})
    uid, handle = user.get("id"), user.get("username")
    if not uid or not handle:
        return f"❌ User fetch error: {user}", 400

    # store
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
      INSERT OR REPLACE INTO twitter_accounts
      (twitter_id,twitter_handle,access_token,refresh_token,token_expiry)
      VALUES (?,?,?,?,?)
    """, (uid, handle, at, rt, exp))
    conn.commit()
    conn.close()

    return f"✅ Connected @{handle}!"

# ─────────────────────────────────────────────────────────────
# Routes: Dashboard, Like, Follow
# ─────────────────────────────────────────────────────────────


@app.route("/", methods=["GET", "POST"])
def dashboard():
    like_results = None
    follow_results = None
    tweet_id = get_setting("tweet_id")
    follow_id = get_setting("follow_target_id")

    if request.method == "POST":
        if "tweet_id" in request.form:
            tweet_id = request.form["tweet_id"]
            set_setting("tweet_id", tweet_id)
            like_results = like_from_accounts(tweet_id)
        if "follow_target_id" in request.form:
            follow_id = request.form["follow_target_id"]
            set_setting("follow_target_id", follow_id)
            follow_results = follow_from_accounts(follow_id)

    # fetch accounts
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT twitter_id, twitter_handle, token_expiry FROM twitter_accounts")
    accounts = cur.fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        accounts=accounts,
        tweet_id=tweet_id,
        follow_id=follow_id,
        like_results=like_results,
        follow_results=follow_results
    )


# ─────────────────────────────────────────────────────────────
# Boot
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup_db()
    app.run(host="0.0.0.0", port=PORT, debug=True)
