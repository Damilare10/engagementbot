# like_post.py
import requests
import sqlite3
import time
import random
from datetime import datetime, timedelta

CLIENT_ID = "dUtBWEVpSC1IX20zZFROOFJiUG06MTpjaQ"
DB_PATH = "twitter_accounts.db"


def refresh_token(refresh_token):
    res = requests.post("https://api.twitter.com/2/oauth2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    if res.status_code != 200:
        print("❌ Refresh failed:", res.status_code, res.text)
        return None
    return res.json()


def like_tweet(access_token, user_id, tweet_id):
    res = requests.post(
        f"https://api.twitter.com/2/users/{user_id}/likes",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"tweet_id": tweet_id}
    )
    return res.status_code, res.text


# Main
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if liking is enabled
cursor.execute("SELECT value FROM settings WHERE key='enabled'")
enabled = cursor.fetchone()[0]
if enabled != "1":
    print("⏸ Liking service is disabled. Exiting.")
    conn.close()
    exit()

# Get tweet ID
cursor.execute("SELECT value FROM settings WHERE key='tweet_id'")
TWEET_ID = cursor.fetchone()[0]

# Get accounts
cursor.execute(
    "SELECT twitter_id, access_token, refresh_token, token_expiry FROM twitter_accounts")
accounts = cursor.fetchall()

for twitter_id, access_token, refresh_token_val, token_expiry in accounts:
    # Refresh if expired
    if datetime.strptime(token_expiry, "%Y-%m-%d %H:%M:%S") < datetime.utcnow():
        token_data = refresh_token(refresh_token_val)
        if not token_data:
            print(f"[{twitter_id}] ❌ Token refresh failed.")
            continue

        access_token = token_data["access_token"]
        refresh_token_val = token_data["refresh_token"]
        new_expiry = datetime.utcnow(
        ) + timedelta(seconds=token_data["expires_in"])

        # Save new tokens
        cursor.execute("""
            UPDATE twitter_accounts
            SET access_token=?, refresh_token=?, token_expiry=?
            WHERE twitter_id=?
        """, (access_token, refresh_token_val, new_expiry.strftime("%Y-%m-%d %H:%M:%S"), twitter_id))
        conn.commit()

    # Attempt like
    status, response = like_tweet(access_token, twitter_id, TWEET_ID)
    print(f"[{twitter_id}] 👍 Like status: {status} → {response}")

    

conn.close()
