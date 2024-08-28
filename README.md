# Social Sync

Attempts to follow your Bluesky (bsky.brid.gy) follows and Threads follows via the Mastodon API

## Setup 
- Clone repo
- `pip install -r requirements.txt` (or use a virtual environment, `python -m virtualenv .venv`, `source .venv/bin/activate`)
- Copy config.toml.example to config.toml.
- Edit Bluesky config with username (or email) and password
- Edit Mastodon config with domain, username, and api_key
- Navigate to Threads account center -> Your Information and permissions -> Download your information -> Download or transfer your information -> Instagram -> Some of your information -> Select Threads -> Export as JSON
- Extract downloaded Threads data
- Copy following.json from instagram-idnumbers/your_instagram_activity/threads/following.json to the cloned repo
- execute `python main.py` this will grab all your follows from both services and saves to a database, then it attempts to follow them all
- The next time you run it, it will just use the database and not use the API
- If you want it to grab the follows again just use `python main.py --refresh`
- I suggest setting it on a cron routine (unfortunately Threads doesn't seem to have API access to the follows so you have to redownload data if you want up-to-date following accounts)
