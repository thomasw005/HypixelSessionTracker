# Program to track session length for a specified player on the Hypixel Network, a Minecraft server.
from pymongo import MongoClient
from pymongo.server_api import ServerApi

import requests
import os
import time
import datetime
from pathlib import Path

# Defining constants
MAX_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 3

BASE_DIR = Path(__file__).resolve().parent
file_path = BASE_DIR / "output.txt"

# MongoDB
MONGO_DB = "hypixel"
MONGO_COLLECTION = "SESSIONS"

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI not set")

client = MongoClient(MONGO_URI, server_api=ServerApi("1"))
db = client[os.getenv("MONGO_DB", "hypixel")]
sessions_col = db[os.getenv("MONGO_COLLECTION", "sessions")]

# Index
sessions_col.create_index([("uuid", 1), ("logout_at", -1)])

API_KEY = os.getenv("HYPIXEL_KEY")
if not API_KEY:
    raise RuntimeError("HYPIXEL_KEY not set")

# Setting up API parameters
url = 'https://api.hypixel.net/v2/status'
headers = {'API-Key': API_KEY}
payload = {'uuid': 'ed4ab730-f132-4511-95c8-d03408d09781'}

session = requests.Session()
session.headers.update(headers)

# Initialziing global variables
online_status = None
start_time = None
unknown_start = False
poll_interval = MIN_POLL_INTERVAL

# Loop to regularly call API
while True:
    try:
        # Get online status of player
        r = session.get(url, params=payload, timeout=10)
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError as e:
            print("Bad JSON:", e)
            poll_interval = min(MAX_POLL_INTERVAL, poll_interval * 1.5) # Backoff
            continue

        polled_online_status = data.get('session', {}).get('online', False)

        # Check initial status of player
        if online_status is None:
            online_status = polled_online_status
            if online_status:
                unknown_start = True
            continue

        # Detect login/out
        if online_status != polled_online_status:
            current_time = datetime.datetime.now(datetime.timezone.utc)

            # Burst poll on login/out
            poll_interval = MIN_POLL_INTERVAL
            
            # Print login/out
            if polled_online_status:
                start_time = current_time
                message_status = f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Logged in."
            else:
                # Calculate session length
                if start_time is None:
                    duration = "Unknown"
                else:
                    duration = current_time - start_time
                message_status = f"[{current_time.strftime('%Y-%m-%d %H:%M:%S')}] Logged out.\nSession length: {duration}"
                
                # If script starts while player was already logged in
                if unknown_start:
                    message_status += "\n!!Unknown Start Time!!"
                
                # Send document to database
                doc = {
                    "uuid": payload["uuid"],
                    "login_at": start_time,
                    "logout_at": current_time,
                    "unknown_start": bool(unknown_start),
                    "created_at": datetime.datetime.now(datetime.timezone.utc),
                }

                if (start_time is None) or (start_time == "Unknown"):
                    doc["duration_seconds"] = None
                    doc["login_at"] = None
                else:
                    doc["duration_seconds"] = int((duration).total_seconds())

                sessions_col.insert_one(doc)
                start_time = None
            unknown_start = False

            # Print player status change, write session length to file
            print(message_status + "\n")
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(message_status + "\n")
            online_status = polled_online_status
        else:
            # Slowly increase poll interval
            poll_interval = min(MAX_POLL_INTERVAL, poll_interval * 1.5)
    
    except requests.RequestException as e:
        poll_interval = min(MAX_POLL_INTERVAL, poll_interval * 1.5) # Backoff
        print("Request failed:", e)

    finally:
        time.sleep(poll_interval)
