# dashboard.py
from flask import Flask, render_template, request, redirect
import sqlite3
import time
import random
import requests
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
DB_PATH = 'twitter_accounts.db'
CLIENT_ID = "dUtBWEVpSC1IX20zZFROOFJiUG06MTpjaQ"

# -------------------------
# Helpers for DB settings
# -------------------------


def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else None


def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# -------------------------
# Refresh + Like functions
# -------------------------


def refresh_token_if_expired(cursor, twitter_id, access_token, refresh_token, expiry_str):
    if datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S") >= datetime.utcnow():
        return access_token

    res = requests.post("https://api.twitter.com/2/oauth2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    if res.status_code != 200:
        return None

    data = res.json()
    new_access_token = data["access_token"]
    new_refresh_token = data["refresh_token"]
    expires_in = data["expires_in"]
    new_expiry = (datetime.now(timezone.utc) +
                  timedelta(seconds=expires_in)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE twitter_accounts SET access_token=?, refresh_token=?, token_expiry=?
        WHERE twitter_id=?
    """, (new_access_token, new_refresh_token, new_expiry, twitter_id))
    return new_access_token


def like_from_accounts(tweet_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT twitter_id, twitter_handle, access_token, refresh_token, token_expiry FROM twitter_accounts")
    accounts = cursor.fetchall()

    results = []

    for twitter_id, handle, token, refresh, expiry in accounts:
        token = refresh_token_if_expired(
            cursor, twitter_id, token, refresh, expiry)
        if not token:
            results.append((handle, "❌ Token Refresh Failed"))
            continue

        res = requests.post(
            f"https://api.twitter.com/2/users/{twitter_id}/likes",
            headers={"Authorization": f"Bearer {token}"},
            json={"tweet_id": tweet_id}
        )

        if res.status_code == 201:
            status = "✅ Liked"
        elif res.status_code == 200 and '"liked":true' in res.text:
            status = "✅ Already Liked"
        else:
            status = f"❌ {res.status_code}: {res.text}"

        results.append((handle, status))
        time.sleep(random.uniform(5.0, 10.0))

    conn.commit()
    conn.close()
    return results


def follow_from_accounts(target_user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT twitter_id, twitter_handle, access_token, refresh_token, token_expiry FROM twitter_accounts")
    accounts = cursor.fetchall()

    results = []

    for twitter_id, handle, token, refresh, expiry in accounts:
        token = refresh_token_if_expired(
            cursor, twitter_id, token, refresh, expiry)
        if not token:
            results.append((handle, "❌ Token Refresh Failed"))
            continue

        res = requests.post(
            f"https://api.twitter.com/2/users/{twitter_id}/following",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_user_id": target_user_id}
        )

        if res.status_code == 200 and '"following":true' in res.text:
            status = "✅ Already Following"
        elif res.status_code == 201:
            status = "✅ Followed"
        else:
            status = f"❌ {res.status_code}: {res.text}"

        results.append((handle, status))

        time.sleep(random.uniform(5.0, 10.0))

    conn.commit()
    conn.close()
    return results


# -------------------------
# Routes
# -------------------------
@app.route('/', methods=['GET', 'POST'])
def dashboard():
    results = None
    tweet_id = get_setting("tweet_id")

    if request.method == 'POST':
        tweet_id = request.form.get("tweet_id")
        set_setting("tweet_id", tweet_id or "")
        results = like_from_accounts(tweet_id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT twitter_id, twitter_handle, token_expiry FROM twitter_accounts")
    accounts = cur.fetchall()
    conn.close()

    return render_template("dashboard.html",
                           accounts=accounts,
                           tweet_id=get_setting("tweet_id"),
                           enabled=(get_setting("enabled") == "1"),
                           follow_results=None,
                           follow_target_id=get_setting("follow_target_id"))


@app.route('/follow_now', methods=['POST'])
def follow_now():
    target_id = request.form.get("follow_target_id")
    if not target_id:
        return "❗ Twitter User ID is required.", 400

    set_setting("follow_target_id", target_id)
    results = follow_from_accounts(target_id)

    # Same dashboard view, but now with follow results
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT twitter_id, twitter_handle, token_expiry FROM twitter_accounts")
    accounts = cur.fetchall()
    conn.close()

    return render_template("dashboard.html",
                           accounts=accounts,
                           tweet_id=get_setting("tweet_id"),
                           results=None,
                           follow_results=results,
                           follow_target_id=target_id)


# -------------------------
# Run
# -------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5001)
