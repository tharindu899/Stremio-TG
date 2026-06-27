---
title: TharinduHub Stremio-TG
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
short_description: Telegram media streaming for Stremio and Nuvio
---

<p align="center">
  <img src="assets/tharinduhub-stremio-banner.svg" alt="TharinduHub • Stremio-TG" width="420" />
</p>

<h1 align="center">🎬 TharinduHub • Stremio-TG</h1>

<p align="center">
  <strong>Private Telegram media library for Stremio &amp; Nuvio</strong><br/>
  Upload to Telegram · Match smart metadata · Stream with personal add-on links
</p>

<p align="center">
  <a href="#quick-start">🚀 Quick Start</a> ·
  <a href="#hugging-face-spaces">🤗 Hugging Face</a> ·
  <a href="#subtitles">💬 Subtitles</a> ·
  <a href="#troubleshooting">🩺 Help</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Web%20API-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/MongoDB-Metadata-47A248?logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/Telegram-Media%20source-26A5E4?logo=telegram&logoColor=white" alt="Telegram" />
  <img src="https://img.shields.io/badge/Stremio-Add--on-8D3DAF?logo=stremio&logoColor=white" alt="Stremio" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

> 💡 **Mobile-first README:** short headings, normal bullet lists, no wide tables, and no unnecessary hidden panels.

---

## ✨ What it does

- 📥 Indexes movies, TV episodes, subtitles, and supported split uploads from Telegram channels.
- 🧠 Matches titles through TMDb/Cinemeta-compatible metadata lookup and filename hints.
- 🗄️ Saves lightweight media references, catalog data, settings, tokens, and subtitle links in MongoDB.
- ⚙️ Serves catalog, metadata, stream, and subtitle endpoints through FastAPI.
- 📺 Lets each user install a private add-on URL in Stremio or Nuvio.
- 🖥️ Includes a web dashboard for media, subtitles, scans, tokens, catalogs, access, and settings.
- 🇱🇰 Uses Sinhala as the subtitle language only when no supported language can be detected.

### 🪄 Media flow

```mermaid
flowchart TB
    A[📥 Telegram channel\nMedia · subtitles · split files]
    B[🤖 Stremio-TG bot + scanner\nDetect · parse · match · index]
    C[(🗄️ MongoDB\nMetadata · stream refs · subtitle links)]
    D[⚙️ FastAPI add-on\nCatalog · meta · streams · subtitles]
    E[📺 Stremio / Nuvio\nBrowse · choose · play]

    A --> B --> C
    C <--> D
    D --> E
```

> 🔒 Your media stays in Telegram. The server stores metadata and Telegram stream references; it does not make a full local copy of your library.

---

## 🚀 Quick Start

1. 🤖 Create a bot with **@BotFather** and add it as an admin in your Telegram media channel.
2. 🔑 Get `API_ID` and `API_HASH` from `my.telegram.org`.
3. 🗄️ Create two MongoDB database names: `dbStremio` and `storage_1` are recommended.
4. 🧩 Add the required startup values in `config.env`, Docker environment variables, or Hugging Face Secrets.
5. 🐳 Deploy with Docker Compose, a VPS, or Hugging Face Spaces.
6. 🖥️ Sign in to the dashboard and set the Base URL, TMDb key, and Auth channels.
7. 📺 Create an access token and install its personal manifest URL in Stremio or Nuvio.

> ⚠️ Change the initial dashboard login immediately. Never share a bot token, MongoDB URI, add-on token, or `USER_SESSION_STRING`.

---

## 🧭 Guide

- 🎬 [How the system works](#how-the-system-works)
- 🔑 [Telegram and MongoDB preparation](#telegram-and-mongodb-preparation)
- 🧩 [Initial configuration](#initial-configuration)
- 🐳 [Docker Compose deployment](#docker-compose)
- 🤗 [Hugging Face Spaces deployment](#hugging-face-spaces)
- 🛡️ [VPS and HTTPS](#vps-and-https)
- 🖥️ [First dashboard setup](#first-dashboard-setup)
- 📺 [Install in Stremio or Nuvio](#install-in-stremio-or-nuvio)
- 📤 [Upload and naming guide](#upload-and-naming-guide)
- 💬 [Subtitle system](#subtitles)
- 🧩 [Split files](#split-files)
- 🔍 [Scans and catalogs](#scans-and-catalogs)
- 🔐 [Tokens and subscriptions](#tokens-and-subscriptions)
- 🌐 [Global Search](#global-search)
- 🩺 [Troubleshooting](#troubleshooting)
- 🔒 [Security checklist](#security-checklist)
- 💙 [Credits](#credits)

---

## ⚙️ How the System Works

### 🗄️ Database roles

`DATABASE` must contain **two comma-separated MongoDB URIs** on first setup:

- **First URI** — tracking database: app settings, tokens, subscriptions, scan state, subtitle index, and dashboard data.
- **Second URI** — `storage_1`: indexed movie and TV stream records.

You can add extra storage databases later from **Admin → Settings**. Keep the first two URIs in their original order.

### 🎛️ Runtime settings

Only startup credentials are needed before the first boot. After the first successful start, the dashboard saves runtime settings in the tracking database.

Set these from **Admin → Settings**:

- 🗂️ Auth channels
- 🎬 TMDb API key
- 🌐 Base URL
- 🔁 Replace Mode and catalog visibility
- 🔐 Dashboard login
- 🌍 Proxy and Global Search settings
- 💳 Subscription settings
- 🤖 Extra bot clients and storage databases

> 📌 Changing runtime values in `config.env` later does not override values already saved in MongoDB.

---

## 🔗 Telegram and MongoDB Preparation

### 🤖 Create the Telegram bot

1. Open **@BotFather**.
2. Send `/newbot` and complete the prompts.
3. Copy the token into `BOT_TOKEN`.
4. Add the bot as an **administrator** in every indexed channel.

For a private channel without a public username, use its numeric `-100…` channel ID in the dashboard.

### 🔑 Get Telegram API values

1. Open `https://my.telegram.org`.
2. Sign in and open **API development tools**.
3. Create an application.
4. Copy the `api_id` and `api_hash` values.

### 👤 Get your Owner ID

Use **@userinfobot** or another trusted Telegram ID bot. Put your numeric account ID in `OWNER_ID`.

### 🗄️ Prepare MongoDB

You can use one MongoDB Atlas cluster with two different database names.

```text
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/dbStremio
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/storage_1
```

- Create a database user with a strong password.
- Add the host network access rule required by your deployment platform.
- URL-encode password characters such as `@`, `:`, `/`, and `#`.
- Keep the complete connection strings private.

---

## 🧩 Initial Configuration

Copy the sample file:

```bash
cp sample_config.env config.env
```

Add only the startup values:

```env
API_ID="1234567"
API_HASH="your_telegram_api_hash"
BOT_TOKEN="1234567890:your_bot_token"
USER_SESSION_STRING=""
OWNER_ID="123456789"
DATABASE="mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/dbStremio,mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/storage_1"
PORT="8000"
```

### 📌 Startup variables

- `API_ID` — **required** Telegram application API ID.
- `API_HASH` — **required** Telegram application API hash.
- `BOT_TOKEN` — **required** main Telegram bot token.
- `OWNER_ID` — **required** numeric Telegram owner ID.
- `DATABASE` — **required** two comma-separated MongoDB URIs: tracking first, `storage_1` second.
- `PORT` — **required** web server port. Use `8000` for Docker/VPS and `7860` for Hugging Face Spaces.
- `USER_SESSION_STRING` — **optional**; required only for Global Search. Treat it like a password.

### ⚠️ Important rules

- Never commit `config.env` or real secrets.
- Do not put secrets in `sample_config.env`.
- Change the default dashboard login at first sign-in.
- Set Base URL, channels, TMDb, and other runtime settings from the dashboard after boot.

---

## 🐳 Docker Compose

### 📦 Deploy

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
cp sample_config.env config.env
nano config.env
docker compose up -d --build
```

Open the dashboard:

```text
http://YOUR_SERVER_IP:8000
```

### 🛠️ Useful commands

```bash
# Follow logs
docker compose logs -f

# Check service state
docker compose ps

# Restart after startup configuration changes
docker compose restart

# Update code and rebuild
git pull
docker compose up -d --build
```

> 🔒 Put the app behind HTTPS before using its address as the final Base URL for Stremio or Nuvio.

---

## 🤗 Hugging Face Spaces

> ✅ This project deploys as a **Docker Space**. Hugging Face reads the YAML card at the top of this `README.md`, builds the root `Dockerfile`, and exposes the configured `app_port`.

### 1. Create the Space

1. Open **Hugging Face → New Space**.
2. Choose your account and a Space name such as `stremio-tg`.
3. Select **Docker** as the SDK.
4. Use a public Space when external Stremio/Nuvio clients need to access the add-on URL.
5. Create the Space.

> 📌 Availability depends on your selected hardware and sleep settings. Choose settings that match the uptime you need for bot activity and playback.

### 2. Keep this README card at the top

```yaml
---
title: TharinduHub Stremio-TG
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
short_description: Telegram media streaming for Stremio and Nuvio
---
```

- `sdk: docker` — tells Hugging Face to build the project Dockerfile.
- `app_port: 7860` — makes the app available at the Space URL.
- `title`, `emoji`, and colors — control the Space card appearance.

### 3. Upload the project

**Browser method**

1. Extract the project ZIP.
2. Open the Space → **Files and versions**.
3. Choose **Add file → Upload files**.
4. Upload the full project while keeping folders intact.
5. Commit the files and watch the build logs.

Upload these project items:

- `Backend/`
- `assets/`
- `Dockerfile`
- `start.sh`
- `pyproject.toml`
- `uv.lock`
- `requirements.txt`
- `sample_config.env`
- `README.md`

Do **not** upload:

- `config.env`
- `.env`
- `*.session`
- Logs, backups, `__pycache__`, or credentials

**Git method**

```bash
git init
git branch -M main
git add -A
git commit -m "Deploy Stremio-TG"
git remote add origin https://huggingface.co/spaces/YOUR-USERNAME/YOUR-SPACE.git
git push -u origin main
```

### 4. Add Secrets and Variable

Open **Space → Settings → Variables and secrets**.

Add these as **Secrets**:

- `API_ID` — Telegram API ID.
- `API_HASH` — Telegram API hash.
- `BOT_TOKEN` — main bot token.
- `OWNER_ID` — numeric Telegram owner ID.
- `DATABASE` — both MongoDB URIs in one comma-separated value.
- `USER_SESSION_STRING` — only when using Global Search.

Add this as a normal **Variable**:

- `PORT` — `7860`

> 🔄 Updating a Space secret, variable, or hardware setting restarts the Space. Secrets are the correct place for credentials; variables are for non-sensitive settings.

### 5. Check the first successful boot

Open **Logs** and confirm these types of messages:

- ✅ Database connections succeed.
- ✅ Telegram client starts.
- ✅ Web server listens on `0.0.0.0:7860`.
- ✅ The public Space URL returns the login page.

Your public address will look like:

```text
https://YOUR-USERNAME-YOUR-SPACE.hf.space
```

### 6. Finish dashboard setup

1. Open the Space URL and sign in.
2. Change the default dashboard login immediately.
3. Open **Admin → Settings**.
4. Set **Base URL** to your complete `.hf.space` URL.
5. Add Auth channel IDs/usernames.
6. Add a TMDb API key.
7. Save settings.

### 🩺 Hugging Face fixes

- **Build fails** — confirm the repository contains `Dockerfile`, `start.sh`, `pyproject.toml`, and `uv.lock` at the root.
- **App opens but does not load** — verify `PORT=7860` and README `app_port: 7860` match.
- **Database error** — recheck both URIs, Atlas user permissions, and network access.
- **Bot does not start** — recheck `API_ID`, `API_HASH`, `BOT_TOKEN`, and `OWNER_ID` Secrets.
- **Playback URL is wrong** — correct the Base URL in dashboard settings and reinstall or refresh the personal manifest.

---

## 🛡️ VPS and HTTPS

### 🌐 Point a domain to the server

Create an `A` record:

```text
Host: @
Value: YOUR_VPS_PUBLIC_IP
```

### 🔐 Use Caddy for HTTPS

Install Caddy, then edit `/etc/caddy/Caddyfile`:

```caddy
your-domain.com {
    reverse_proxy localhost:8000
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy
```

Finally set this in **Admin → Settings → Base URL**:

```text
https://your-domain.com
```

---

## 🖥️ First Dashboard Setup

Open the deployment URL. The initial login is usually:

```text
Username: admin
Password: admin
```

Change it immediately.

### ✅ Essential settings

- **Base URL** — your public HTTPS domain or `.hf.space` URL.
- **Auth channels** — Telegram channels to index and stream from.
- **TMDb API key** — improves movie and series matching.
- **Replace Mode** — recommended on; newer files can replace matching title/episode/quality entries.
- **Catalog visibility** — choose whether the general catalog is visible.

### ➕ Optional settings

- **Extra storage databases** — expand stream-reference storage.
- **Additional bot clients** — more parallel capacity during higher load.
- **Subscriptions** — plan, approval, expiry, and membership checks.
- **Proxy** — use for outbound metadata requests where needed.
- **Global Search** — requires `USER_SESSION_STRING` and selected channel IDs.

---

## 📺 Install in Stremio or Nuvio

### 🔑 Create a token

1. Open **Admin → Access Management**.
2. Create a token or assign one to a user.
3. Copy its personal manifest URL.

Standard URL pattern:

```text
https://YOUR-DOMAIN/stremio/YOUR-TOKEN/manifest.json
```

### 🎬 Stremio

1. Open Stremio.
2. Go to **Add-ons**.
3. Paste the personal manifest URL.
4. Install or update it.

### 📺 Nuvio

1. Open Nuvio.
2. Open **Add-ons**.
3. Paste the same personal manifest URL.
4. Install it and open your library.

> 🔐 Give each user a separate token. Revoke a token immediately if it is exposed.

---

## 📤 Upload and Naming Guide

### 🎞️ Movies

Use a clean title and year whenever possible:

```text
Movie Title (2026) 1080p WEB-DL x265.mkv
```

Useful optional tags: resolution, source, codec, audio, and release group.

### 📺 TV episodes

Always include a season and episode marker:

```text
Series Title S01E04 1080p WEB-DL.mkv
```

Both `S01E04` and `S01 E04` are clear. Keep the same series name across episodes.

### 🛠️ Correct wrong metadata

- Open **Media Management → Edit** and use metadata search.
- Or use `/set <IMDb-or-TMDb-URL>` before forwarding the related upload batch.
- Send `/set` with no URL to clear the temporary override.

---

## 💬 Subtitles

### 📄 Supported formats

- `.srt`
- `.vtt`
- `.ass`
- `.ssa`
- `.sub`
- `.smi`
- `.sami`

### 🌍 Language detection

The scanner reads language names and well-known language codes from the subtitle filename and caption.

Examples:

```text
Movie Title (2026).Sinhala.srt
Movie Title (2026).si.srt
Series Title S01E01.Japanese.srt
Movie Title (2026).Arabic.srt
```

### 🇱🇰 Sinhala fallback

- An explicitly detected language such as English, Japanese, Arabic, Tamil, Hindi, Malayalam, Telugu, or Sinhala always stays unchanged.
- A truly unlabelled subtitle defaults to **Sinhala (`si`)**.
- An uploader/group suffix is not treated as a language just because it looks like a short code.

### 🧬 Matching order

The subtitle matcher uses safe signals in this order:

1. Explicit subtitle tag or IMDb/TMDb ID.
2. Exact movie title and year.
3. Series title with `SxxEyy` episode marker.
4. Cleaned filename matching after removing release noise.
5. Metadata aliases, including romanized or localized titles.
6. Manual relink from the dashboard.

### 🏷️ Guaranteed manual subtitle link

Add a tag anywhere in the subtitle caption or filename:

```text
[SUB:tt1234567 si]
```

- `tt1234567` — target IMDb ID.
- `si` — subtitle language code.

### 🔄 Repair unmatched subtitles

1. Make sure the matching movie or episode is already indexed.
2. Open **Subtitles**.
3. Select **Match unmatched**.
4. Use manual match/edit when the file needs a specific target.

> 💡 A subtitle marked **unmatched** is still stored safely; it simply has no verified media target yet.

---

## 🧩 Split Files

The scanner supports common multipart archive names such as:

```text
Movie.Title.2026.mkv.zip.001
Movie.Title.2026.mkv.zip.002
```

For reliable virtual playback:

- Upload every part to the same indexed channel.
- Keep the base filename identical across all parts.
- Do not rename only one volume.
- Complete the upload before running a scan.
- Run a Media or Full scan if the grouped virtual stream does not appear yet.

---

## 🔍 Scans and Catalogs

### 🔎 Scan tools

Use **Admin → Tools**:

- **Media scan** — video files and split media.
- **Subtitle scan** — subtitle documents only.
- **Full scan** — media, subtitles, and supported split groups.
- **Targeted scan** — use after a small upload or correction.

Scan again after:

- Adding a new channel.
- Fixing file captions or filenames.
- Updating subtitle matching code.
- Uploading all parts of a split archive.
- Moving or restoring content.

### 🗃️ Catalogs

- Create custom catalogs from the dashboard.
- Enable automatic catalog synchronization only for the catalogs you want.
- Catalog quick sync can skip already-classified files; this is normal.
- Use Media Management to correct a title that was classified incorrectly.

### 🔗 Dead links

The background checker validates existing Telegram references. Use dashboard tools to review and repair/remove unavailable entries when a source message has been deleted or become unreachable.

---

## 🔐 Tokens and Subscriptions

### 🔑 Access tokens

- Create individual personal tokens from **Access Management**.
- Set expiry or revoke access when needed.
- Delete and recreate a token if it was shared publicly.
- Share only the user’s personal manifest URL.

### 💳 Optional subscriptions

When subscription mode is enabled:

- Users choose a plan through the bot.
- They submit payment proof.
- Approved users receive a personal add-on URL.
- Expired users are prompted to renew through the bot.
- Optional group-membership checks can restrict streaming to subscribed channel members.

Configure plans, approver IDs, payment text, and group settings from the dashboard.

---

## 🌐 Global Search

Global Search needs a Telegram user-session client.

1. Set `USER_SESSION_STRING` before startup.
2. Restart the application.
3. Enable Global Search from dashboard settings.
4. Add the channel IDs to search.

> ⚠️ A user session can access your Telegram account. Keep it private, revoke it from Telegram Devices if exposed, and use it only for channels you are allowed to access.

---

## 🤖 Bot Commands

- `/start` — provides the available add-on access flow.
- `/set <IMDb-or-TMDb-URL>` — sets temporary metadata for the next related uploads.
- `/set` — clears the temporary metadata override.
- `/stats` — owner statistics.
- `/log` — sends the current log to the owner.
- `/restart` — runs the configured restart/update workflow.
- `/status` — subscription status when subscription mode is enabled.

> ✅ Command availability depends on your role and enabled features.

---

## 🖥️ Dashboard Pages

- `/` — main dashboard and service overview.
- `/media/manage` — browse, edit, rescan, and remove media.
- `/subtitles` — search, filter, edit, relink, match, or delete subtitles.
- `/catalogs` — manage custom catalogs and auto-sync.
- `/admin/access` — manage tokens and access.
- `/admin/subscriptions` — plans and subscription users.
- `/admin/settings` — runtime configuration.
- `/admin/tools` — scans, checks, and maintenance.
- `/status` — public service status.

> 🔐 A `302 Found` redirect to `/login` for protected dashboard APIs is normal when you are signed out.

---

## 🩺 Troubleshooting

### 🔐 Dashboard sends you to `/login`

Your dashboard session is missing or expired. Sign in again. A `302 Found` for protected API routes is expected security behavior.

### ✅ Manifest pinger shows `Status: 200`

This is healthy: the public add-on manifest is reachable.

### 🧠 Metadata is wrong or missing

- Set TMDb API key and Base URL.
- Open **Media Management → Edit** and run metadata search.
- Use `/set` with the correct IMDb/TMDb URL for the next upload batch.
- Use clean title, year, and `SxxEyy` naming.

### 💬 Subtitle is indexed but unmatched

- Index the matching movie or episode first.
- Add a clear title/year or `SxxEyy` marker.
- Add `[SUB:tt… language]` for a guaranteed link.
- Open **Subtitles → Match unmatched**.

### 🌍 Subtitle language is wrong

- Add a clear language name such as `Sinhala`, `English`, `Arabic`, or `Japanese`.
- Use a recognized code such as `.si`, `.en`, `.ar`, or `.ja`.
- Edit the subtitle record from the dashboard if needed.

### 🤖 Bot does not index files

- Confirm channel is in **Auth channels**.
- Confirm bot is an admin and can see channel messages.
- Run the correct scan scope from **Admin → Tools**.
- Use `/log` as owner to check the exact error.

### 🧩 Split upload is not one stream

- Confirm all volumes exist.
- Keep matching base filenames.
- Keep all volumes in the same channel.
- Run a Media or Full scan after the upload completes.

### 🚫 Invalid or expired API token

Create a fresh token in Access Management, install its manifest URL, and revoke the old one when appropriate.

### 🗄️ MongoDB connection fails

- Check both URIs are present and separated by one comma.
- URL-encode password special characters.
- Check Atlas database-user permissions and network rules.

---

## 🔒 Security Checklist

- [ ] Change the default dashboard login.
- [ ] Keep `config.env` and secrets outside Git history.
- [ ] Use platform Secrets for credentials.
- [ ] Use a strong MongoDB password.
- [ ] Use HTTPS for the Base URL.
- [ ] Keep Telegram source channels private unless intentionally public.
- [ ] Give each user a separate manifest token.
- [ ] Revoke leaked tokens immediately.
- [ ] Protect `USER_SESSION_STRING` like a Telegram password.
- [ ] Back up MongoDB before bulk scans or destructive cleanup.

---

## 🗂️ Project Layout

```text
.
├── Backend/                 # FastAPI, Telegram clients, scans, metadata, subtitles
├── assets/                  # Branding assets
├── Dockerfile               # Docker image
├── docker-compose.yaml      # Docker Compose setup
├── sample_config.env        # Startup configuration template
├── start.sh                 # Container startup command
├── pyproject.toml           # Python dependencies
└── README.md                # This guide
```

---

## 🔄 Update Safely

1. Back up tracking and storage MongoDB databases.
2. Keep a secure copy of secrets/configuration.
3. Pull or upload the new project code.
4. Rebuild and restart the service.
5. Confirm dashboard settings, Base URL, channels, and access tokens.
6. Run **Match unmatched** after a subtitle-matcher update.
7. Run targeted scans only when necessary.

Docker Compose update:

```bash
git pull
docker compose up -d --build
docker compose logs -f
```

---

## 💙 Credits

<p align="center">
  <a href="https://github.com/weebzone/Telegram-Stremio">
    <img src="https://img.shields.io/badge/%F0%9F%92%99%20Forked%20from-weebzone%2FTelegram--Stremio-0D1117?style=for-the-badge&logo=github&logoColor=white" alt="Forked from weebzone/Telegram-Stremio" />
  </a>
</p>

> 💙 **Forked from [weebzone/Telegram-Stremio](https://github.com/weebzone/Telegram-Stremio)**  
> Original project foundation by **Weebzone** — customized and maintained by [**tharindu899**](https://github.com/tharindu899).

- 🎬 **Stremio** — add-on ecosystem and playback clients.
- ⚡ **FastAPI** — web API and dashboard.
- 🍃 **MongoDB** — metadata, settings, tokens, subtitles, and catalogs.
- 🤗 **Hugging Face Spaces** — Docker deployment option.

---

## 📜 License

Distributed under the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE).

<p align="center">
  <strong>🎬 TharinduHub • Stremio-TG</strong><br/>
  <sub>Private Telegram library · Smart metadata · Better subtitles</sub><br/>
  <sub>💙 Forked from <a href="https://github.com/weebzone/Telegram-Stremio">weebzone/Telegram-Stremio</a> · Customized by <a href="https://github.com/tharindu899">tharindu899</a></sub>
</p>
