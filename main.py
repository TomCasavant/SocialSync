from atproto import Client
from mastodon import Mastodon
import enum
import toml
import sqlite3
import json
import argparse

BLUESKY_BRIDGE="bsky.brid.gy" # Will probably not work when custom handles exist
THREADS_DOMAIN="threads.net" # Threads does not present users in the @threads.net format so we have to append this

import sqlite3

class UserDB:

    db_file = "following_cache.db"

    def __init__(self):
        self._initialize_database()

    def _initialize_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS follows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handle TEXT NOT NULL,
                platform TEXT NOT NULL,
                followed BOOLEAN NOT NULL,
                UNIQUE(handle, platform)
            )
        ''')
        conn.commit()
        conn.close()

    def save_follows_to_cache(self, follows):
        print("Saving follows to cache")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.executemany('''
            INSERT OR IGNORE INTO follows (handle, platform, followed)
            VALUES (?, ?, ?)
        ''', [(follow['handle'], follow['platform'], False) for follow in follows])
        conn.commit()
        conn.close()

    def load_follows_from_cache(self, platform):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM follows WHERE platform = ?', (platform,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def set_followed_status(self, follow):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE follows
            SET followed = ?
            WHERE handle = ? AND platform = ?
        ''', (follow['followed'], follow['handle'], follow['platform']))
        conn.commit()
        conn.close()

    def remove_platform_followers(self, platform):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM follows WHERE platform = ?', (platform,))
        conn.commit()
        conn.close()

class Platform:

    DOMAIN = ""
    
    def __init__(self, db, platform):
        self.db = db
        self.platform = platform
        self._follows = None  # Cache the followers

    @property
    def follows(self):
        if self._follows is None:
            self._follows = self.db.load_follows_from_cache(self.platform)
            if not self._follows:
                self._follows = self.fetch_follows()
                self.db.save_follows_to_cache(self._follows)
        return self._follows

    def refresh_follows(self):
        print(f"Clearing out all follows for {self.platform}")
        self.db.remove_platform_followers(self.platform)

    def fetch_follows(self):
        raise NotImplementedError("This method should be implemented by subclasses")

    def to_fedi_handle(self, handle):
        return f"@{handle}@{self.DOMAIN}"

class Bluesky(Platform):

    DOMAIN = "bsky.brid.gy"

    def __init__(self, username, password, db):
        super().__init__(db, 'bluesky')
        self.client = Client()
        self.login(username, password)

    def fetch_follows(self):
            print("Fetching followers from Bluesky API")
            follows = []
            req = self.client.get_follows(self.client.me.handle)
            follows.extend({'handle': follow.handle, 'platform': self.platform, 'followed': False} for follow in req.follows)
            while req.cursor is not None:
                req = self.client.get_follows(self.client.me.handle, req.cursor)
                follows.extend({'handle': follow.handle, 'platform': self.platform, 'followed': False} for follow in req.follows)
            return follows

    def login(self, username, password):
        self.client.login(username, password)

class Threads(Platform):

    DOMAIN = "threads.net"

    def __init__(self, json_file_path, db):
        super().__init__(db, 'threads')
        self.json_file_path = json_file_path

    def fetch_follows(self):
        print("Fetching followers from JSON file for Threads")
        follows = []
        with open(self.json_file_path, 'r') as file:
            data = json.load(file)
            for entry in data.get("text_post_app_text_post_app_following", []):
                for string_data in entry.get("string_list_data", []):
                    username = string_data.get("value")
                    if username:
                        follows.append({
                            'handle': username,
                            'platform': self.platform,
                            'followed': False
                        })
        return follows


class MastodonUser:

    def __init__(self, base_url, access_token, db=None):
        self.mastodon = Mastodon(api_base_url=base_url, access_token=access_token)
        self.db = db

    def normalize_handle(self, handle):
        if handle[0] == '@':
            return handle[1:]
        return handle

    def follow_user(self, handle, follow):
        normal_handle = self.normalize_handle(handle)
        print(f"Attempting to follow {normal_handle}")
        users = None
        try:
            users = self.mastodon.account_search(normal_handle, resolve=True)
        except Exception as e:
            print(f"Failed to search for user {e}")
        if users:
            for user in users:
                if user['acct'] == normal_handle:
                    print("Discovered User, attempting follow...")
                    try:
                        self.mastodon.account_follow(user['id'])
                        follow['followed'] = True
                        self.db.set_followed_status(follow)
                        return
                    except Exception as e:
                        print(f"Failed to follow: {e}")
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Social Sync")
    parser.add_argument('--refresh', action='store_true', help='Clear out follows from database')
    args = parser.parse_args()

    # Load configuration
    config = toml.load("config.toml")

    # Instantiate database
    db = UserDB()

    # Bluesky account
    bluesky_config = config["Bluesky"]
    bluesky = Bluesky(bluesky_config["username"], bluesky_config["password"], db)

    # Threads account
    threads_config = config["Threads"]
    threads = Threads(threads_config["json_file"], db)

    if args.refresh:
        bluesky.refresh_follows()
        threads.refresh_follows()

    # Mastodon account
    mastodon_config = config["Mastodon"]
    mastodonAcc = MastodonUser(mastodon_config["domain"], mastodon_config["api_key"], db)

    # Follow users from Bluesky
    for user in bluesky.follows:
        mastodonAcc.follow_user(bluesky.to_fedi_handle(user['handle']), user)

    # Follow users from Threads
    for user in threads.follows:
        mastodonAcc.follow_user(threads.to_fedi_handle(user['handle']), user)
