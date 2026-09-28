# Deploying Stock Fundamentals so friends can use it

The simplest free setup is **Streamlit Community Cloud** (hosts the app) plus **Neon** (free hosted
Postgres for accounts and the request log). About 20 minutes, no credit card.

Why a hosted database: Streamlit Cloud wipes the app's local files whenever it restarts, so the
built-in SQLite file would lose every account and request. Neon keeps them.

## 1. Put the code on GitHub

1. Create a **private** repository on github.com (e.g. `stock-fundamentals`).
2. Upload everything in this folder **except** `.venv`, `cache`, `data` and `settings.json`
   (the included `.gitignore` already excludes them if you use Git or GitHub Desktop).

## 2. Create the database (Neon)

1. Sign up at https://neon.tech and create a project.
2. Copy the connection string it shows. It looks like
   `postgresql://user:password@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require`

The app creates its tables automatically on first start.

## 3. Deploy the app (Streamlit Community Cloud)

1. Sign in at https://share.streamlit.io with your GitHub account.
2. **Create app** → pick your repository → main file `app.py`.
3. Open **Advanced settings → Secrets** and paste (with your values):

   ```toml
   DATABASE_URL = "postgresql://...your Neon string..."
   SEC_USER_AGENT = "Pat Brown you@example.com"
   ADMIN_SETUP_CODE = "pick-a-long-private-code"
   ```

4. Deploy. You get a URL like `https://your-app.streamlit.app`.

## 4. First sign-in and invites

1. Open the URL, expand **Owner setup**, enter your `ADMIN_SETUP_CODE` and create your account. It
   becomes the **admin**. Nobody else can do this without the code, and the option disappears once
   your account exists.
2. Go to **Admin → Invites**, create an invite per friend (or one with several uses), and send them
   the link. Sign-up is invite-only.
3. **Admin → Usage** shows which equities people request, which competitors they compare, requests
   per day, and a per-user breakdown. The full log downloads as CSV.

## Notes

- **Stay signed in:** logins are remembered for 30 days with a browser cookie. If a host or browser
  blocks that cookie, people simply sign in again on each visit.
- **Yahoo Finance from cloud servers:** Yahoo sometimes rate-limits shared cloud IPs. When that
  happens, price-based ratios (P/E, PEG, returns) show "—" for a while; the SEC fundamentals still load.
- **SEC limits:** the SEC allows 10 requests/second per server. The app stays under that and caches
  everything, so a handful of friends is no problem.
- **Other hosts:** anything that runs a Python web app works (Render, Railway, Fly.io, a VPS). Start
  command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`, with the same two
  environment variables.
- **Running locally still works** exactly as before (`run.bat`). Without `DATABASE_URL` it uses a
  local SQLite file in `data/`.
