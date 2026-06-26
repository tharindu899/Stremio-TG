---
title: Stremio-TG
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: gpl-3.0
---

<p align="center">
  <img src="assets/stremio-tg-banner.svg" alt="TharinduHub Stremio-TG banner" width="100%" />
</p>

<p align="center">
  <img src="assets/stremio-tg-icon.svg" alt="Stremio-TG app icon" width="116" />
</p>

<h1 align="center">Stremio-TG</h1>
<p align="center"><strong>A private Telegram media library, streaming gateway, and Stremio add-on control room.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/runtime-v3.6.15-7c6cff?style=for-the-badge" alt="Runtime v3.6.15" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-WebUI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/MongoDB-Storage-47A248?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/Stremio-Addon-6C43E0?style=for-the-badge" alt="Stremio" />
  <img src="https://img.shields.io/badge/PWA-Online--only-5A0FC8?style=for-the-badge" alt="Online-only PWA" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-3DA639?style=for-the-badge" alt="GPL-3.0" />
</p>

> [!IMPORTANT]
> This project indexes and streams files that **you are authorized to access and distribute**. It does not provide media files, torrent sources, or an unauthorised content catalogue. Keep the bot, MongoDB, add-on tokens, and `USER_SESSION_STRING` private.

---

## 🧭 Table of contents

- [What Stremio-TG does](#-what-stremio-tg-does)
- [Feature map](#-feature-map)
- [Architecture](#-architecture)
- [Source-based release notes](#-source-based-release-notes)
- [Requirements](#-requirements)
- [Quick start](#-quick-start)
- [Configuration reference](#-configuration-reference)
- [Deployment](#-deployment)
- [First-run checklist](#-first-run-checklist)
- [Telegram bot commands](#-telegram-bot-commands)
- [Media, metadata, subtitles, and split files](#-media-metadata-subtitles-and-split-files)
- [WebUI guide](#-webui-guide)
- [Stremio add-on and delivery routes](#-stremio-add-on-and-delivery-routes)
- [Subscriptions, tokens, and access](#-subscriptions-tokens-and-access)
- [Global search and multi-client streaming](#-global-search-and-multi-client-streaming)
- [PWA assets](#-pwa-assets)
- [Operations, backup, updates, and troubleshooting](#-operations-backup-updates-and-troubleshooting)
- [Project map](#-project-map)
- [License](#-license)

---

## ✨ What Stremio-TG does

Stremio-TG is a self-hosted bridge between your Telegram media channels and Stremio. A PyroFork bot observes authorised Telegram channels, identifies supported video and subtitle uploads, stores metadata and delivery references in MongoDB, and exposes a personal tokenized Stremio add-on URL for each viewer.

| Area | Implemented behavior in this build |
|---|---|
| 🎬 **Media ingestion** | Indexes new and edited Telegram channel videos/documents; removes records when channel messages are deleted. |
| 🔎 **Metadata matching** | Uses parsed filenames, IMDb/TMDb data, aliases, fuzzy-title scoring, and manual repair workflows. |
| 🗂️ **Media library** | Stores movies, TV shows, seasons, episodes, qualities, Telegram message references, and database-node location. |
| 🈂️ **Subtitles** | Indexes subtitle documents separately, detects languages, matches them to movies/episodes, supports manual linking, and exposes Stremio subtitle resources. |
| 🗜️ **Split files** | Supports virtual streaming for split media parts and split ZIP volumes without joining files on disk. |
| 📺 **Stremio** | Serves tokenized manifest, catalog, meta, stream, subtitle, and delivery endpoints. |
| 📊 **WebUI** | Includes dashboard, media manager, subtitle library, catalogs, operations, scanner tools, access, subscriptions, settings, and mobile navigation. |
| 🔐 **Viewer access** | Creates/revokes API tokens, tracks daily/monthly usage, optionally links tokens to Telegram users and subscription status. |
| ⚡ **Streaming** | Uses HTTP Range requests, Telegram DC-aware client selection, dynamic prefetch/parallelism, live stream metrics, and dead-link checks. |
| 📱 **PWA** | Provides installable app metadata and app icons. It is intentionally network-only: no media or page cache is stored for offline use. |

### What it is not

- It is **not** a general file host; Telegram remains the media source.
- It is **not** an offline video downloader.
- It is **not** an open public add-on by default; each viewer needs a tokenized manifest URL.
- It does **not** automatically make an inaccessible private Telegram channel available to a bot or user account.

---

## 🧩 Feature map

| Feature | Where you use it | Notes |
|---|---|---|
| Live channel indexing | Telegram channel + **Settings** | Add the bot as admin and save the numeric channel ID under allowed channels. |
| Full, media-only, or subtitle-only scans | **Scanner Tools** | Normal scans can resume from a saved cursor; rescans clear matching index rows first. |
| Manual metadata repair | **Edit Media** or `/set` | The Edit Media flow changes database metadata only. `/set` temporarily adds a default IMDb/TMDb reference to new uploads. |
| Quality management | **Edit Media** | Delete a movie quality, TV episode, TV season, or individual TV quality entry. |
| Subtitle review | **Subtitles** | Filter by status/language, edit language, relink, manually attach IDs, or delete. |
| Custom shelves | **Catalogs** | Create named catalogs and add indexed movies or series manually. |
| Auto catalogs | **Catalogs** | Language, smart, and provider shelves are classified through TMDb data after you save a selection. |
| Viewer tokens | **Overview** / **Access** | Token links are personal manifest URLs; usage limits use `0` for unlimited. |
| Subscription plans | **Subscriptions** / Telegram bot | Viewer chooses a plan, sends a screenshot, and an approver accepts or rejects it. |
| Global search | **Settings** + `USER_SESSION_STRING` | Searches extra channels through the signed-in user account; it is not enabled unless both session and channels exist. |
| Multiple bot clients | **Settings** | Additional bot tokens are started as no-update stream clients for higher delivery capacity. |
| Dead-link repair | **Operations** / **Scanner Tools** | The scheduled checker marks broken streams; tools can verify and purge dead references. |

---

## 🏗️ Architecture

```mermaid
flowchart LR
    A[Telegram media channels] -->|new / edited video or subtitle| B[PyroFork StreamBot]
    B --> C[Filename + metadata parser]
    C --> D[(MongoDB tracking DB)]
    C --> E[(MongoDB storage DBs)]
    E --> F[FastAPI WebUI]
    E --> G[Stremio addon routes]
    H[Optional Userbot session] -->|global search / fallback| G
    I[Extra bot tokens] -->|parallel Telegram delivery| J[Range streaming engine]
    G --> J
    J --> K[Stremio client]
```

### Core request flow

1. A video, document, or subtitle is posted to an authorised Telegram channel.
2. The receiver checks whether it is a supported media file, subtitle, or split archive part.
3. The filename/caption is parsed for title, year, season, episode, quality, language, and any manual ID hint.
4. Metadata is resolved and a document is written or updated in the active MongoDB storage node.
5. A Stremio client requests a personal manifest URL, then requests catalogs, metadata, streams, or subtitles.
6. A stream URL resolves the stored Telegram message reference. The server honours HTTP Range requests and selects the most suitable available Telegram client.
7. Usage and stream diagnostics are written to the tracking database.

---

## 🧾 Source-based release notes

This README is written against the files in this repository, not against an external feature list.

| Item | Current source value | Why it matters |
|---|---:|---|
| Runtime version | `3.6.15` in `Backend/__init__.py` | This is the version reported by the running FastAPI app and bot statistics command. |
| `pyproject.toml` version | `3.5.3` | Align this with `3.6.15` before making a formal release tag. |
| Python requirement | `>=3.11` | Use Python 3.11 or newer. |
| Database name | `dbStremio` | Each configured MongoDB URI uses this database name. |
| Required databases | Minimum **2** URIs | URI #1 is tracking; URI #2 becomes `storage_1`. Extra nodes are supported. |
| Timezone code | `Asia/Kolkata` in current source | Change source values deliberately if your deployment standard is different. |
| PWA mode | Online-only | The service worker clears old caches and serves network requests with `no-store`. |
| Auto catalog interval | 60 minutes | It starts only after at least one auto-catalog selection has been saved. |

> [!WARNING]
> `start.sh` runs `uv run update.py` before the app starts. If an `UPSTREAM_REPO` is configured, `update.py` can reset the working tree to the configured branch. Keep `UPSTREAM_REPO` empty unless you intentionally want automatic upstream replacement.

---

## ✅ Requirements

### Accounts and services

| Requirement | Required | Purpose |
|---|:---:|---|
| Telegram API ID + API hash | ✅ | Connects the PyroFork bot and optional Userbot. |
| Telegram bot token | ✅ | Watches authorised channels and serves bot interactions. |
| Telegram owner numeric ID | ✅ | Restricts owner-only bot commands. |
| Two MongoDB connection URIs | ✅ | Tracking database plus first media storage node. |
| Public HTTPS URL | ✅ for usable Stremio links | Required as the public base URL for installation and delivery. |
| TMDb v3 API key | Strongly recommended | Needed for reliable metadata and automatic catalog classification. |
| User session string | Optional | Required only for global search / Userbot fallback. |
| Additional bot tokens | Optional | Adds delivery clients; configure after boot in WebUI settings. |

### Local tools

| Tool | Recommended version | Used for |
|---|---:|---|
| Python | 3.11+ | Application runtime. |
| `uv` | Current stable | Dependency sync and launch scripts. |
| Docker + Docker Compose | Current stable | Repeatable local/VPS deployment. |
| Git | Current stable | Version control and deployments. |
| Caddy or another reverse proxy | Current stable | HTTPS on a VPS/domain. |

---

## 🚀 Quick start

### 1) Clone and prepare the app

```bash
git clone <your-repository-url> Stremio-TG
cd Stremio-TG
cp sample_config.env config.env
```

### 2) Fill the startup configuration

Open `config.env` and provide the required values:

```env
# Telegram — required
API_ID="123456"
API_HASH="your_telegram_api_hash"
BOT_TOKEN="123456:bot_token_here"
USER_SESSION_STRING=""  # optional: required only for Global Search
OWNER_ID="123456789"

# MongoDB — minimum 2 comma-separated URIs
DATABASE="mongodb+srv://user:password@cluster.example.net/,mongodb+srv://user:password@cluster.example.net/"

# Server
PORT="8000"
```

### 3) Install and start without the automatic updater

```bash
uv sync
uv run -m Backend
```

Use this direct command while developing. It starts the application without calling `update.py` first.

### 4) Open the WebUI

```text
http://127.0.0.1:8000/login
```

The first-start defaults in the source are `admin` / `admin`. Change them immediately in **Settings → Administrator and access channels**.

### 5) Complete the first-run checklist

Follow [First-run checklist](#-first-run-checklist) before uploading media or giving viewers a Stremio manifest URL.

---

## ⚙️ Configuration reference

### Startup-critical values — `config.env`

These values are read before the application can connect its core services.

| Variable | Required | Example / format | Used for |
|---|:---:|---|---|
| `API_ID` | ✅ | `123456` | Telegram application API ID. |
| `API_HASH` | ✅ | text string | Telegram application API hash. |
| `BOT_TOKEN` | ✅ | `123456:ABC...` | Main StreamBot token. |
| `OWNER_ID` | ✅ | numeric Telegram user ID | Restricts `/stats`, `/log`, `/restart`, and `/set`. |
| `DATABASE` | ✅ | `uri_tracking,uri_storage_1` | Minimum two comma-separated MongoDB URIs. |
| `PORT` | ✅ | `8000` locally / `7860` in a Docker Space | Uvicorn listener port. |
| `USER_SESSION_STRING` | Optional | Pyrogram session string | Enables optional Userbot global search/fallback. |

### First-boot seed values

On the **first** successful startup, the app stores runtime settings in the tracking database. The variables below seed those settings. After that, the WebUI becomes the normal place to manage them.

| Variable | Default in source | WebUI equivalent | Notes |
|---|---|---|---|
| `REPLACE_MODE` | `true` | Library behavior | Lets incoming quality updates replace matching media logic. |
| `HIDE_CATALOG` | `false` | Library behavior | Removes Stremio catalog/meta resources; stream/subtitle resources remain. |
| `AUTH_CHANNEL` | empty | Required channels | Comma-separated channel IDs used for ingest. Use numeric `-100…` IDs for reliable live indexing. |
| `TMDB_API` | empty | Metadata and source | TMDb v3 key for matching and auto catalogs. |
| `BASE_URL` | empty | Metadata and source | Public HTTPS origin used by bot-generated manifest links. |
| `UPSTREAM_REPO` | empty | Metadata and source | Enables `update.py` upstream reset behavior. |
| `UPSTREAM_BRANCH` | empty | Metadata and source | Branch used by `update.py`; defaults to `master` when blank. |
| `ADMIN_USERNAME` | `admin` | Administrator and access channels | WebUI administrator username. |
| `ADMIN_PASSWORD` | `admin` | Administrator and access channels | WebUI administrator password. Change before exposing the service. |
| `SUBSCRIPTION` | `false` | Subscription access | Enables plan, payment screenshot, and expiry checks. |
| `SUBSCRIPTION_GROUP_ID` | `0` | Subscription access | Group/channel used for approved subscriber invitation links. |
| `SUBSCRIPTION_URL` | `https://t.me/` | Subscription access | Renewal destination used for expired streams. |
| `APPROVER_IDS` | empty | Subscription access | Comma-separated Telegram user IDs allowed to approve/reject payments. |
| `HTTP_Proxy_URL` | empty | Proxy | Optional URL prefix used for delivery proxying. |
| `SHOW_ProxyAndNonProxyBoth` | `false` | Proxy | Shows both direct and proxy stream choices when proxy is configured. |

> [!CAUTION]
> The live Telegram receiver compares `str(message.chat.id)` to the authorised-channel list. Although the UI placeholder accepts a username, a full numeric `-100…` channel ID is the dependable format for live indexing.

### Runtime-only settings in the WebUI

| Setting | What it changes live |
|---|---|
| **Allowed channels** | Which Telegram channel message IDs are accepted for live indexing and scanner selection. |
| **Extra databases** | Additional storage nodes beyond `storage_1`; the app reconnects them from the tracking settings. |
| **Multi bot tokens** | Additional bot clients used for streaming capacity; saves trigger a reload of client connections. |
| **Global search + channels** | Enables Userbot searches only when `USER_SESSION_STRING` is available and at least one numeric channel is configured. |
| **Subscription / plans / approvers** | Controls protected access, plan flow, payment review, expiry, and invitation. |
| **Auto catalog selection** | Stores chosen language, smart, and provider shelves; changes trigger new classification revision. |
| **Theme** | Changes the WebUI appearance through a per-session theme control. |

### Secure `config.env` example

```env
# Required core values
API_ID="123456"
API_HASH="replace_me"
BOT_TOKEN="replace_me"
OWNER_ID="123456789"
DATABASE="mongodb+srv://user:password@tracking.example.net/,mongodb+srv://user:password@storage.example.net/"
PORT="8000"

# Optional Userbot / first-start seed values
USER_SESSION_STRING=""
TMDB_API=""
BASE_URL="https://media.example.com"
AUTH_CHANNEL="-1001234567890"
ADMIN_USERNAME="change_this"
ADMIN_PASSWORD="use_a_long_unique_password"

# Keep blank unless you intentionally accept upstream reset updates
UPSTREAM_REPO=""
UPSTREAM_BRANCH=""
```

---

## ☁️ Deployment

### Local development with `uv`

```bash
cd Stremio-TG
cp sample_config.env config.env
# edit config.env
uv sync
uv run -m Backend
```

Useful local commands:

```bash
# Check that Python source compiles
uv run python -m compileall Backend

# Remove generated Python bytecode after a check
find Backend -type d -name '__pycache__' -prune -exec rm -rf {} +

# See the working tree
 git status
```

### Docker Compose — recommended for a VPS or home server

The repository includes `docker-compose.yaml` with service name `telegram-stremio` and container name `tg_stremio`.

```bash
cp sample_config.env config.env
# edit config.env first
docker compose up -d --build
```

Operational commands:

```bash
# Follow application logs
docker compose logs -f

# Show service state
docker compose ps

# Restart after changing startup config
docker compose restart

# Rebuild after source changes
docker compose up -d --build

# Stop the stack
docker compose down

# Open a shell inside the running container
docker compose exec telegram-stremio bash
```

### Docker CLI

```bash
docker build -t stremio-tg:local .

docker run -d \
  --name tg_stremio \
  --restart unless-stopped \
  --env-file config.env \
  -p 8000:8000 \
  stremio-tg:local
```

### Hugging Face Docker Space

This README already contains Docker Space metadata, including `sdk: docker` and `app_port: 7860`.

1. Create a **Docker** Space.
2. Push this repository to the Space.
3. In **Settings → Variables and secrets**, add the startup values below as **Secrets**.
4. Set `PORT` to `7860` so Uvicorn listens on the Space application port.
5. Set `BASE_URL` to the Space’s public HTTPS origin after the Space is available.
6. Push or restart; the Space rebuilds from the Dockerfile.

| Hugging Face Secret | Required |
|---|:---:|
| `API_ID` | ✅ |
| `API_HASH` | ✅ |
| `BOT_TOKEN` | ✅ |
| `OWNER_ID` | ✅ |
| `DATABASE` | ✅ |
| `PORT` = `7860` | ✅ |
| `USER_SESSION_STRING` | Optional |

> [!TIP]
> Hugging Face Docker Spaces use the README YAML block for Space configuration and expose runtime Secrets/Variables through the container environment. The official Docker Space reference is linked in [Hugging Face Docker Spaces documentation](https://huggingface.co/docs/hub/spaces-sdks-docker).

### VPS with Caddy reverse proxy

Keep the application private behind HTTPS. The following assumes the app listens only on local port `8000` and Caddy owns TLS.

```caddyfile
media.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then reload Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Set this exact public origin in WebUI settings:

```text
https://media.example.com
```

### Git commands for your own repository

```bash
git init
git add -A
git commit -m "Initial Stremio-TG setup"
git branch -M main
git remote add origin <your-repository-url>
git push -u origin main
```

> [!WARNING]
> Do not commit `config.env`, Telegram session files, tokens, database URLs, or `.restartmsg`. The supplied `.gitignore` already excludes the main sensitive local files.

---

## 🧪 First-run checklist

### 1. Secure the WebUI

1. Open `/login`.
2. Sign in using the first-start credentials.
3. Open **Settings**.
4. Replace both administrator username and password with unique values.
5. Save settings and sign in again to verify the new credentials.

### 2. Connect Telegram safely

1. Add the main bot to every library channel you want it to observe.
2. Give it the permissions required to receive channel posts and edit its own message where applicable.
3. Add each channel using its full numeric ID, for example `-1001234567890`, in **Settings → Required channels**.
4. Save settings.
5. Upload one small test video or subtitle to verify that indexing begins.

### 3. Configure metadata and public URLs

1. Add your TMDb v3 key under **Settings → Metadata and source**.
2. Add the exact public HTTPS `BASE_URL` used by Stremio.
3. Save settings.
4. Use **Scanner Tools** to run a small scan or upload a new cleanly named file.

### 4. Create your first viewer token

1. Open **Overview**.
2. Create a token for yourself.
3. Copy its manifest URL.
4. Open the URL in a Stremio client and install the add-on.
5. Play a test stream and open **Operations** to confirm a playback event appears.

### 5. Test captions and split files

- Upload a normal subtitle and confirm that it appears in **Subtitles**.
- Attach an explicit subtitle ID tag if matching needs help.
- Upload all parts of a split file with consistent names before testing playback.

---

## 🤖 Telegram bot commands

### Viewer commands

| Command | Who can use it | Actual behavior |
|---|---|---|
| `/start` | Owner when subscriptions are off; viewers when subscriptions are on | With subscriptions off, only `OWNER_ID` receives a personal add-on URL. With subscriptions on, inactive viewers see plans; active viewers receive their linked add-on URL. |
| `/status` | Subscription viewers | Returns current subscription state and remaining time. It does nothing when subscriptions are disabled. |

### Owner-only commands

| Command | Purpose | Use it correctly |
|---|---|---|
| `/stats` | Shows movie, TV, episode, stream, database-size, uptime, storage-node, and authorised-channel statistics. | Send in the bot’s private chat as `OWNER_ID`. |
| `/log` | Sends the current `log.txt` as a document. | Use for diagnostics; logs may contain operational details. |
| `/restart` | Runs `uv run update.py`, writes restart-notification state, then execs `uv run -m Backend`. | Use only after understanding the automatic updater warning. |
| `/set <IMDb-or-TMDb-URL>` | Sets a temporary default ID reference for subsequent relevant uploads. | Use for a batch that has wrong/ambiguous names. |
| `/set` | Clears the temporary default ID reference. | Always clear it after the intended upload batch. |

### `/set` example

```text
/set https://www.imdb.com/title/tt1234567/
```

Upload the related movie or series files, then clear the temporary override:

```text
/set
```

The receiver appends the current default reference to new relevant uploads, then the edited-message handler reprocesses the metadata with that explicit reference.

---

## 🎞️ Media, metadata, subtitles, and split files

### Supported media intake

The live receiver accepts:

| Telegram post type | Accepted condition |
|---|---|
| Telegram video | Accepted. |
| Telegram document | Accepted when MIME type begins with `video/`. |
| Split file document | Accepted when recognised as a supported split media/archive part, including common ZIP/octet-stream volumes. |
| Subtitle document | Routed to subtitle indexing when it matches the subtitle detector. |

Video filenames are normalized to a common media extension where needed. Typical supported video forms include MKV, MP4, AVI, TS, M4V, MOV, WMV, WebM, FLV, MPEG, and MPG.

### Safe movie filename pattern

```text
Movie Title (2026) 1080p WEB-DL x265 AAC.mkv
```

### Safe series filename pattern

```text
Series Title S01E01 1080p WEB-DL x265 AAC.mkv
```

### Metadata matching order

1. Explicit manual reference from caption/default `/set` workflow.
2. Filename parsing for title, year, season, episode, quality, and release details.
3. Candidate matching through IMDb/TMDb data and alias-aware fuzzy scoring.
4. Manual repair from **Edit Media → Repair metadata match** if the automatic result is wrong.

### Fixing a wrong match

| Situation | Best action |
|---|---|
| One incorrect title already indexed | Open **Media Library → Edit Media → Repair metadata match**. |
| A whole upload batch has confusing file names | Use `/set <IMDb/TMDb URL>`, upload batch, then `/set` to clear. |
| Existing channel history was not indexed | Run a targeted scan from **Scanner Tools**. |
| A clean filename still fails | Use an explicit matching reference and re-upload/edit, or use the repair workflow. |

### Subtitle naming and matching

Subtitle parsing uses caption and filename information. It recognizes language labels, IMDb IDs, TMDb IDs, SxxExx / `1x02`, release year, and explicit subtitle tags.

| Best practice | Example |
|---|---|
| Movie subtitle | `Example Film (2026) Sinhala sub.srt` |
| Episode subtitle | `Example Show S01E02 Arabic.srt` |
| Explicit IMDb tag | `Example Show S01E02 [SUB:tt1234567 si].srt` |
| Explicit TMDb tag | `Example Film [SUB:tmdb:12345 ar].srt` |
| Caption-assisted tag | File name can stay simple when the Telegram caption contains `[SUB:tt1234567 S01E02 en]`. |

> [!TIP]
> Subtitle filenames do **not** need a resolution. Clear title + season/episode + language is more useful than release-quality labels.

### Subtitle workflow

1. Upload the subtitle as a Telegram document to an authorised channel.
2. Open **Subtitles** and confirm its detected language/status.
3. Use **Relink** after scanning or after the matching video is available.
4. For a stubborn file, open the manual link dialog and supply IMDb ID, optional season/episode, and language.
5. In Stremio, the subtitle resource returns every subtitle linked to that movie or episode across its qualities.

### Split raw media

Use consistent part names. Examples:

```text
Example.Film.2026.1080p.mkv.001
Example.Film.2026.1080p.mkv.002
Example.Film.2026.1080p.mkv.003
```

### Split ZIP media

The project can inspect and stream supported ZIP-volume content virtually; no server-side merge/extract is expected for playback.

```text
Example.Film.2026.2160p.mkv.zip.001
Example.Film.2026.2160p.mkv.zip.002
Example.Film.2026.2160p.mkv.zip.003
```

Rules for dependable split playback:

1. Upload **every** volume to the same authorised channel.
2. Keep one consistent base name and ordered numeric suffixes.
3. Do not rename one part independently after upload.
4. Wait until the final part is indexed before playback testing.
5. Use **Scanner Tools** if historical parts were posted before the channel was configured.

---

## 🖥️ WebUI guide

### Navigation map

| Page | What it is for | Main actions |
|---|---|---|
| **Overview** | Daily library and token home | Storage-node status, active streams, create/edit/revoke viewer tokens, copy manifest links. |
| **Media Library** | Browse indexed movies or series | Search, paginate, open a record, inspect its metadata and files. |
| **Edit Media** | Per-record management | Update metadata fields, repair title match, manage custom catalog placement, delete media qualities/episodes/seasons, run DC speed test. |
| **Subtitles** | Caption quality control | Inspect totals, filter by matching status/language, search all indexed subtitle documents, relink, manually link, update language, delete. |
| **Catalogs** | Curate Stremio shelves | Save auto-catalog choices, create custom shelves, search library, add/remove records, trigger sync. |
| **Operations** | Runtime visibility | Bot client load, current/recent streams, stream analytics, dead-link review, cache/analytics maintenance. |
| **Scanner Tools** | Channel history and integrity jobs | Choose channels, start/cancel/resume scan or rescan, run DB checks, purge dead links. |
| **Access** | Viewer and subscription access | Search token/user records, link tokens to Telegram users, assign plans, extend/revoke access. |
| **Subscriptions** | Plans and subscribers | Create/edit/delete plans and manage subscriber state. |
| **Settings** | Runtime configuration | Library behavior, auth channels, admin credentials, metadata, source, proxy, subscription, global search, multi-token, database nodes. |

### Scanner modes

| Mode | Content scope | Meaning |
|---|---|---|
| **Scan** | Media / Subtitles / Everything | Reads channel history from the saved cursor when possible; cancellation is resumable. |
| **Rescan** | Media / Subtitles / Everything | Clears only the selected scope’s indexed records for selected channels, then rebuilds from history. |
| **DB check** | Indexed streams | Verifies stored Telegram references and records dead ones for repair/purge. |

At scan completion, the manager enters a **finalizing** phase, relinks unmatched subtitles, reconciles subtitle counters, then marks the job complete. This avoids declaring 100% completion before subtitle linking is finished.

### Auto-catalog choices

| Group | Available shelves |
|---|---|
| **Language** | Bollywood, Hollywood, Anime, K-Drama, Bengali, South Indian, Tamil, Telugu, Malayalam, Kannada, Japanese, Korean. |
| **Smart** | Top Rated, Recently Added. |
| **OTT** | Netflix, Prime Video, Hotstar, Apple TV, Hulu, HBO, JioCinema, ZEE5, SonyLIV, MX Player, Crunchyroll. |

The auto-catalog region is currently `IN`. A saved catalog-selection revision tells the next quick/full sync to re-evaluate older indexed media when options change.

---

## 🎬 Stremio add-on and delivery routes

### Personal manifest URL

```text
https://your-public-host/stremio/<viewer-token>/manifest.json
```

Each token represents a viewer. Treat it like a password: anyone holding it can request the corresponding add-on routes until you revoke it.

### Add-on endpoints

| Route | Purpose |
|---|---|
| `GET /stremio/{token}/manifest.json` | Dynamic personal Stremio manifest. |
| `GET /stremio/{token}/configure` | Browser-friendly reinstall/configure page. |
| `GET /stremio/{token}/catalog/{type}/{id}.json` | Tokenized movie/series catalog resource. |
| `GET /stremio/{token}/meta/{type}/{id}.json` | Movie or series metadata resource. |
| `GET /stremio/{token}/stream/{type}/{id}.json` | Stream choices for a movie or episode. |
| `GET /stremio/{token}/subtitles/{type}/{id}.json` | Linked subtitle choices; accepts Stremio’s extra video context too. |
| `GET /dl/{token}/{id}/{name}` | Byte-range media/subtitle delivery endpoint. |

### Manifest behavior

- When **Hide catalog** is off, the manifest exposes `catalog`, `meta`, `stream`, and `subtitles` resources.
- When **Hide catalog** is on, it exposes only `stream` and `subtitles` resources.
- Custom catalogs are dynamically added as movie and series catalog entries.
- When subscriptions are enabled, an active viewer’s expiry is reflected in the add-on name/description.
- Expired subscription or usage-limit states return a visible Stremio stream item rather than a normal playable media list.

### Stream naming

The current Stremio stream label format is:

```text
[Stremio-TG] • 2160p Blu-ray
```

The detail area contains filename, source size, and parsed codec/bit-depth/audio information. Split streams use a distinct archive/package indicator.

---

## 🔐 Subscriptions, tokens, and access

### Viewer tokens

| Function | Result |
|---|---|
| Create token | Generates a tokenized Stremio manifest URL. |
| Set daily/monthly limit | `0` means unlimited; positive values are checked against accumulated transfer bytes. |
| Revoke token | Immediately prevents new requests using that token. |
| Link token to Telegram user | Needed when subscription enforcement is enabled. |
| Assign/extend/revoke subscription | Updates the viewer’s active status and expiry. |

### Subscription payment path

```mermaid
sequenceDiagram
    participant V as Viewer
    participant B as Telegram bot
    participant A as Approver
    participant S as Stremio-TG
    V->>B: /start
    B->>V: Select plan
    V->>B: Sends payment screenshot
    B->>A: Forwards screenshot + Approve/Reject buttons
    A->>B: Approves or rejects
    B->>S: Writes subscription state and token link
    B->>V: Sends expiry, install URL, and optional group invite
```

### Subscription setup order

1. Enable **Subscription** in Settings.
2. Add at least one subscription plan in **Subscriptions**.
3. Set `SUBSCRIPTION_GROUP_ID` if approved users should receive an invite.
4. Add one or more approver numeric IDs.
5. Confirm `/start` works for a test user.
6. Create/verify token linkage before testing Stremio playback.

---

## 🌐 Global search and multi-client streaming

### Global search

Global search is an optional fallback. It looks for a requested title in additional Telegram channels through the configured **Userbot**, then returns matching result streams when no local stream exists.

Requirements:

1. `USER_SESSION_STRING` must be set at startup.
2. **Global search** must be enabled in Settings.
3. At least one numeric channel ID must be saved in **Global search channels**.
4. The user account behind the session must be able to access those channels.
5. Result filenames must pass title/episode matching checks.

Global searches have a cooldown and concurrent-search guard to reduce Telegram request pressure.

### Multiple streaming clients

| Capability | Behavior |
|---|---|
| Main client | Uses `BOT_TOKEN` as client index `0`. |
| Extra clients | WebUI `multi_tokens` creates additional no-update PyroFork bot clients. |
| DC preference | Tries clients connected to the target Telegram data center first. |
| Load selection | Scores current load plus recent failures, then round-robins tied clients. |
| Dynamic parallelism | Uses a bounded calculation based on extra client count; prefetch and parallelism are clamped between `1` and `5`. |
| Failure decay | Client failure scores drop gradually every five minutes. |
| Diagnostics | WebUI exposes client load, current/recent streams, transfer speed, duration, and state. |

> [!NOTE]
> Extra bot tokens improve delivery-client availability; they do not grant access to channels that the relevant bot cannot access.

---

## 📱 PWA assets

The WebUI now includes a matching Stremio-TG PWA asset set:

| File | Purpose |
|---|---|
| `assets/stremio-tg-banner.svg` | README / project banner. |
| `assets/stremio-tg-icon.svg` | Reusable high-resolution vector brand icon. |
| `Backend/fastapi/static/icons/stremio-tg-icon.svg` | WebUI vector icon source. |
| `Backend/fastapi/static/icons/favicon.svg` | Modern SVG favicon. |
| `Backend/fastapi/static/icons/favicon.ico` | Fallback favicon bundle. |
| `Backend/fastapi/static/icons/icon-192.png` | Standard + maskable PWA icon. |
| `Backend/fastapi/static/icons/icon-512.png` | Large standard + maskable PWA icon. |
| `Backend/fastapi/static/icons/apple-touch-icon.png` | iOS home-screen icon. |
| `Backend/fastapi/static/manifest.webmanifest` | Install metadata and icon declarations. |

The PWA service worker intentionally uses network-only requests. Installing the WebUI provides an app-like shell and icon, but it does **not** cache pages, media, API responses, or login data for offline use.

---

## 🛠️ Operations, backup, updates, and troubleshooting

### Back up MongoDB

Back up both the tracking database and every storage database. The application database name is `dbStremio`.

```bash
# Example: snapshot the tracking database
mongodump \
  --uri "mongodb+srv://user:password@tracking.example.net/" \
  --db dbStremio \
  --out ./backups/tracking-$(date +%F)

# Example: snapshot a storage database
mongodump \
  --uri "mongodb+srv://user:password@storage.example.net/" \
  --db dbStremio \
  --out ./backups/storage-1-$(date +%F)
```

### Update behavior

| Method | Command | Important detail |
|---|---|---|
| Direct normal start | `uv run -m Backend` | Does not run updater first. |
| Scripted start | `bash start.sh` | Runs `uv run update.py && uv run -m Backend`. |
| Bot restart | `/restart` | Runs `update.py` before execing the app. |
| Docker rebuild | `docker compose up -d --build` | Rebuilds from the checked-out source. |

`update.py` reads `UPSTREAM_REPO` / `UPSTREAM_BRANCH` from database settings first, then the environment. When an upstream is configured, it initializes Git and resets hard to the selected remote branch. Keep this disabled for a customized local fork unless automatic overwrite is truly desired.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `At least 2 database URIs are required` | `DATABASE` contains fewer than two valid URIs. | Provide tracking URI first and `storage_1` URI second. |
| Bot does not index a channel upload | Channel was not saved as numeric ID, bot lacks channel access, or live event happened before settings were saved. | Use full `-100…` ID, grant bot channel access, then run a targeted scan. |
| File says metadata failed | Filename/caption lacks a usable title or matches the wrong item. | Use `/set <IMDb/TMDb URL>`, clean filename, or repair metadata from Edit Media. |
| Subtitle appears unmatched | Movie/episode has not been indexed yet or title/episode/language hints are weak. | Upload matching media, run **Relink**, or set manual IMDb ID + episode. |
| Split stream does not play | A part is missing or part base names do not match. | Upload all numbered parts with identical base naming, then rescan/index. |
| Stremio manifest opens but playback is empty | Token invalid/expired, subscription expired, usage limit reached, or no local match. | Check Access, subscription state, token limits, and Operations logs. |
| `/start` gives no link | Subscription mode is off and caller is not `OWNER_ID`, or `BASE_URL` is empty. | Use the owner account or enable subscription flow; configure public Base URL. |
| Global search returns nothing | Userbot is unavailable, account cannot access target channel, global search disabled, or filename match is weak. | Validate session, membership, channel IDs, and title/episode format. |
| Restart unexpectedly replaces changes | Upstream repository is configured. | Clear upstream settings and deploy your own branch. |
| PWA does not refresh after icon/style change | Browser cached a static icon or old install metadata. | Reload, clear site data, remove/reinstall the PWA, then reopen. |

### Security checklist

- [ ] Use a long unique WebUI administrator password.
- [ ] Keep `config.env`, bot tokens, MongoDB URLs, and Userbot session strings out of Git.
- [ ] Use a private HTTPS origin; do not expose a raw development port publicly.
- [ ] Revoke a viewer token immediately when access should end.
- [ ] Use separate tokens for viewers instead of sharing one manifest URL.
- [ ] Limit Telegram channel and Userbot membership to media you control.
- [ ] Keep `UPSTREAM_REPO` empty unless automatic reset-based updating is intentional.
- [ ] Back up tracking and all storage nodes before schema or source changes.

---

## 📁 Project map

```text
Stremio-TG/
├── Backend/
│   ├── __main__.py                 # Service lifecycle: DB, bot, web server, background jobs
│   ├── config.py                   # Startup environment configuration
│   ├── logger.py                   # Application logging
│   ├── fastapi/
│   │   ├── main.py                 # FastAPI app, WebUI, PWA, admin API registration
│   │   ├── routes/
│   │   │   ├── stremio_routes.py   # Manifest, catalog, meta, streams, configure page
│   │   │   ├── stream_routes.py    # HTTP Range delivery, client selection, analytics
│   │   │   ├── subtitle_routes.py  # Stremio subtitle resource
│   │   │   ├── subtitle_api_routes.py # Subtitle-management API
│   │   │   ├── api_routes.py       # Admin/media/settings/tools/catalog API
│   │   │   └── template_routes.py  # Web page rendering and login routes
│   │   ├── security/               # Admin session and token verification
│   │   ├── templates/              # Responsive HTML pages for every WebUI section
│   │   ├── static/
│   │   │   ├── css/                # App + page-specific styles
│   │   │   ├── js/                 # App + page-specific client behavior
│   │   │   ├── icons/              # PWA and favicon assets
│   │   │   ├── manifest.webmanifest
│   │   │   └── service-worker.js   # Deliberately online-only service worker
│   │   └── themes.py               # WebUI color themes
│   ├── helper/
│   │   ├── database.py             # MongoDB storage, tokens, media, subtitles, analytics
│   │   ├── metadata.py             # Filename, alias, IMDb/TMDb matching
│   │   ├── scan_manager.py         # Resumable channel scanner and DB checker
│   │   ├── subtitle_*.py           # Language parsing, matching, models, service layer
│   │   ├── split_files.py          # Split-name detection and metadata fields
│   │   ├── archive_split.py        # Virtual ZIP-volume inspection/streaming
│   │   ├── virtual_dl.py           # Virtual ranged concatenated media delivery
│   │   ├── custom_dl.py            # Telegram byte streaming and speed testing
│   │   ├── global_search.py        # Optional Userbot channel search
│   │   ├── auto_catalog.py         # Custom/automatic catalog classification and interval loop
│   │   ├── link_checker.py         # Scheduled dead-link checking
│   │   └── settings_manager.py     # Runtime settings stored in tracking MongoDB
│   └── pyrofork/
│       ├── bot.py                  # Main bot/Userbot definitions and client status maps
│       ├── clients.py              # Extra streaming bot lifecycle
│       └── plugins/                # Telegram handlers: receive, commands, subscriptions
├── assets/
│   ├── stremio-tg-banner.svg       # New README banner
│   └── stremio-tg-icon.svg         # Reusable vector app icon
├── Dockerfile                      # uv-based container image
├── docker-compose.yaml             # Local/VPS compose service
├── sample_config.env               # Minimal startup env template
├── start.sh                        # Update + startup script
├── update.py                       # Optional upstream reset/update flow
├── pyproject.toml                  # Python package metadata/dependencies
├── requirements.txt                # Compatibility dependency list
├── uv.lock                         # Locked uv dependency state
└── LICENSE                         # GNU GPL v3.0
```

---

## 🧰 Admin API groups

The browser UI uses these protected administrative API families after a valid WebUI session is established.

| API family | Representative paths |
|---|---|
| Media | `/api/media/list`, `/api/media/update`, `/api/media/delete`, `/api/media/rescan/*` |
| Subtitles | `/api/subtitles`, `/api/subtitles/stats`, `/api/subtitles/relink` |
| Tokens & access | `/api/tokens`, `/api/admin/access/tokens`, `/api/admin/access/users/{user_id}/assign-plan` |
| System & operations | `/api/system/stats`, `/api/admin/system-stats`, `/api/admin/stream-analytics`, `/api/admin/dead-links` |
| Subscriptions | `/api/admin/subscriptions/plans`, `/api/admin/subscriptions/users` |
| Catalogs | `/api/custom-catalogs`, `/api/custom-catalogs/auto-sync`, `/api/custom-catalogs/auto-sync/settings` |
| Runtime settings | `/api/admin/settings` |
| Scanner & integrity tools | `/api/admin/tools/channels`, `/api/admin/tools/scan/*`, `/api/admin/tools/dbcheck/*`, `/api/admin/tools/dead-links/purge` |

Use the WebUI for normal operations. API calls are intended for the integrated frontend and require an authenticated browser session.

---

## 📜 License

This repository includes the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE) for the complete terms.

---

<p align="center">
  <strong>TharinduHub · Stremio-TG</strong><br/>
  Built for a clean private media-library workflow: Telegram → MongoDB → Stremio.
</p>
