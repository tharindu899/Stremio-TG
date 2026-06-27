---
title: TharinduHub • Stremio-TG
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
short_description: TharinduHub Telegram streaming with smart subtitles
---

<p align="center">
  <img src="assets/tharinduhub-stremio-banner.svg" alt="TharinduHub · Stremio-TG" width="760" />
</p>

<h1 align="center">🎬 TharinduHub • Stremio-TG</h1>

<p align="center">
  <strong>⚡ Your private Telegram media library for Stremio &amp; Nuvio</strong><br />
  Upload to Telegram • Index with smart metadata • Stream with personal add-on links • Manage everything from one beautiful dashboard
</p>

<p align="center">
  <a href="#quick-start"><strong>🚀 Quick Start</strong></a> ·
  <a href="#deploy-with-docker-compose"><strong>🐳 Docker</strong></a> ·
  <a href="#deploy-on-hugging-face-spaces"><strong>🤗 Hugging Face</strong></a> ·
  <a href="#subtitle-system"><strong>💬 Subtitles</strong></a> ·
  <a href="#troubleshooting"><strong>🩺 Help</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-Web%20API-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/MongoDB-Storage-47A248?logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/Telegram-Media%20source-26A5E4?logo=telegram&logoColor=white" alt="Telegram" />
  <img src="https://img.shields.io/badge/Stremio-Add--on-8D3DAF?logo=stremio&logoColor=white" alt="Stremio" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-GPL--3.0-blue" alt="GPL-3.0" />
</p>

<p align="center">
  <strong>🌟 Brand:</strong> <a href="https://t.me/TharinduHub">TharinduHub</a>
</p>

<table align="center">
  <tr>
    <td align="center"><strong>📚 Telegram Storage</strong><br /><sub>Keep your library in channels</sub></td>
    <td align="center"><strong>⚡ Direct Streaming</strong><br /><sub>Fast Stremio &amp; Nuvio playback</sub></td>
    <td align="center"><strong>💬 Smart Subtitles</strong><br /><sub>Auto-match + Sinhala fallback</sub></td>
    <td align="center"><strong>🖥️ Web Dashboard</strong><br /><sub>Manage from any device</sub></td>
  </tr>
</table>

> 💡 **TharinduHub private-library design:** your media stays in Telegram, while MongoDB stores only the metadata and stream references.

---

<a id="quick-start"></a>
## 🚀 Quick Start

1. 🤖 Create a Telegram bot with **@BotFather** and add it as an admin in your media channel.
2. 🗄️ Create two MongoDB databases: one for **tracking** and one for **storage**.
3. 🧩 Fill the required values in `config.env` or your hosting platform secrets.
4. 🐳 Deploy with Docker, 🤗 Hugging Face Spaces, or a VPS.
5. 🖥️ Open the dashboard, configure your **Base URL**, **TMDb key**, and **Auth channels**.
6. 📺 Create a personal token and install the manifest in **Stremio** or **Nuvio**.

> ⚠️ **Before sharing access:** change the default dashboard login and never publish your bot token, MongoDB URI, or `USER_SESSION_STRING`.

---

<a id="contents"></a>
## 🧭 Quick Navigation

| 🚀 Start Here | ⚙️ Setup & Deploy | 🎬 Library & Playback |
|---|---|---|
| [🎬 What Stremio-TG Does](#what-stremio-tg-does) | [🧰 Requirements](#requirements) | [📤 Upload & Naming Guide](#upload-and-naming-guide) |
| [✨ Feature Overview](#feature-overview) | [🔗 Telegram & MongoDB](#telegram-and-mongodb-preparation) | [💬 Subtitle System](#subtitle-system) |
| [⚙️ How It Works](#how-the-system-works) | [🧩 Initial Configuration](#initial-configuration) | [🧩 Split Files](#split-files-and-archive-volumes) |
| [🖥️ Dashboard Setup](#first-run-dashboard-setup) | [🐳 Docker Compose](#deploy-with-docker-compose) | [🔍 Scans & Catalogs](#scanning-matching-and-catalog-tools) |
| [📺 Add Stremio / Nuvio](#add-stremio-or-nuvio) | [🤗 Hugging Face Spaces](#deploy-on-hugging-face-spaces) | [🔐 Tokens & Subscriptions](#access-tokens-and-subscriptions) |
| [🤖 Bot Commands](#bot-commands) | [🛡️ VPS + HTTPS](#deploy-on-a-vps-with-https) | [🌐 Global Search](#global-search) |

| 🧭 Manage & Maintain | 🔒 Keep It Safe |
|---|---|
| [🖥️ Dashboard Pages](#dashboard-pages) · [🩺 Troubleshooting](#troubleshooting) · [🔄 Updating Safely](#updating-safely) | [🔒 Security Checklist](#security-checklist) · [🗂️ Project Layout](#project-layout) · [🙏 Credits](#credits) · [📜 License](#license) |

---

<a id="what-stremio-tg-does"></a>
## 🎬 What Stremio-TG Does

Stremio-TG turns Telegram channels into a private media library.

1. You add the bot as an administrator in one or more media channels.
2. The server indexes video files, subtitle documents, and supported multipart uploads.
3. It resolves movie or TV metadata through the configured metadata provider.
4. It stores stream references in MongoDB rather than downloading the media to your server.
5. Stremio or Nuvio uses your personal add-on URL to browse, stream, and load linked subtitles.

```text
📥 Telegram channel
      │
      ▼
🤖 Stremio-TG bot + scanner
      │
      ▼
🗄️ MongoDB metadata and stream references
      │
      ▼
⚙️ FastAPI add-on endpoints
      │
      ▼
📺 Stremio / Nuvio playback
```

> ⚖️ **Use responsibly:** Stremio-TG is intended for media you are authorized to store and access. Keep Telegram channels, database credentials, bot tokens, and add-on tokens private.

---

<a id="feature-overview"></a>
## ✨ Feature Overview

### 📚 Telegram Media Library

- 📚 Index movies and TV episodes from one or more Telegram channels.
- 📚 Keep stream references in MongoDB; no local media disk is required.
- 📚 Support normal video uploads and compatible document uploads.
- 📚 Show compact stream labels such as `[Stremio-TG] • 2160p WEB-DL`.
- 📚 Replace an existing stream when a newer file has the same title, episode, and quality while **Replace Mode** is enabled.
- 📚 Detect common split uploads and expose them as one virtual stream instead of separate parts.
- 📚 Run dead-link checks and remove or repair unavailable source messages from the library.

### 🧠 Metadata, Catalogs & Search

- 🧠 Resolve movies and series through TMDb/Cinemeta-compatible metadata matching.
- 🧠 Match noisy filenames with year, quality, season, and episode hints.
- 🧠 Manually correct a wrong title from the media editor or with an IMDb/TMDb URL.
- 🧠 Create custom catalogs, manage catalog content, and use automatic catalog synchronization.
- 🧠 Browse latest and popular content through the Stremio add-on.
- 🧠 Optional Telegram **Global Search** using a personal user-session client and selected channels.

### 💬 Subtitle Library

- 💬 Index `.srt`, `.vtt`, `.ass`, `.ssa`, `.sub`, `.smi`, and `.sami` subtitle files.
- 💬 Detect movie and episode subtitles from filename, caption, explicit IDs, season/episode markers, year, and metadata aliases.
- 💬 Support title aliases such as romanized, localized, and English metadata names.
- 💬 Keep explicit subtitle languages correct, including Sinhala, English, Japanese, Arabic, Tamil, Hindi, Malayalam, Telugu, and more.
- 💬 Use **Sinhala (`si`) as the default only when no supported language can be detected** in the filename or caption.
- 💬 Provide a subtitle page with filters, search, pagination, edit, delete, manual matching, and **Match unmatched** relinking.
- 💬 Return linked subtitles to Stremio for every quality of the same movie or episode.

### 🖥️ Web Dashboard

- 🖥️ Mobile-friendly dashboard with light and dark themes.
- 🖥️ Media management for movies and series.
- 🖥️ Subtitle management with status and language filters.
- 🖥️ Catalog editor and auto-sync controls.
- 🖥️ Scan tools for media-only, subtitle-only, and full channel scans.
- 🖥️ Access-token management, stream analytics, dead-link tools, system statistics, and settings.
- 🖥️ PWA assets for an installable dashboard experience.

### 🔐 Access & Subscriptions

- 🔐 Personal Stremio add-on tokens.
- 🔐 Optional user subscription plans, payment proof flow, approver actions, access expiry, and channel membership checks.
- 🔐 Add or revoke access from the dashboard.
- 🔐 Optional stream data limits per token.
- 🔐 Extra storage databases and additional bot clients can be added from runtime settings.

---

<a id="how-the-system-works"></a>
## ⚙️ How the System Works

### 🗄️ Data Storage Roles

The required `DATABASE` value contains two comma-separated MongoDB URIs:

| Database position | Purpose |
|---|---|
| First URI | Tracking database: app settings, tokens, subscriptions, scan state, subtitle index, and administrative data. |
| Second URI | `storage_1`: movie and TV stream records. |

Additional storage databases can be added later from **Admin → Settings**. The first two URIs remain the required tracking and initial storage databases.

### 🎛️ Runtime Settings

> 💡 **Good to know:** only the startup credentials are required before the first run. On the first successful boot, the remaining runtime settings are seeded into the tracking database.

After that, use the dashboard for runtime settings such as channels, TMDb API key, base URL, catalog behavior, proxy, subscriptions, and additional bot tokens. Editing legacy runtime values in `config.env` after first boot does not overwrite the settings already stored in MongoDB.

---

<a id="requirements"></a>
## 🧰 Requirements

Before deployment, prepare:

- 🧰 A Telegram bot token from **@BotFather**.
- 🧰 Telegram `API_ID` and `API_HASH` from `my.telegram.org`.
- 🧰 Your numeric Telegram user ID for `OWNER_ID`.
- 🧰 A MongoDB deployment reachable by the server. MongoDB Atlas M0 is suitable for a small personal library.
- 🧰 At least one Telegram channel where the bot is an administrator.
- 🧰 A public HTTPS URL for reliable Stremio/Nuvio playback. A Hugging Face Space URL or VPS domain is suitable.
- 🧰 A TMDb API key for accurate automated metadata and catalog operations.

Optional:

- 🧰 A `USER_SESSION_STRING` for Global Search.
- 🧰 Extra bot tokens for more streaming clients.
- 🧰 A subscription group, approver IDs, payment instructions, and payment QR image URL for paid/private access.

---

<a id="telegram-and-mongodb-preparation"></a>
## 🔗 Telegram & MongoDB Preparation

### 🤖 1. Create the Telegram Bot

1. Open **@BotFather** in Telegram.
2. Send `/newbot` and complete the prompts.
3. Copy the generated token into `BOT_TOKEN`.
4. Add the bot as an **administrator** in every channel it must index or stream from.

The bot needs enough channel permissions to read the media messages it indexes. For private channels, use the numeric channel ID if a public `@username` is unavailable.

### 🔑 2. Get `API_ID` & `API_HASH`

1. Open `https://my.telegram.org`.
2. Sign in with your Telegram phone number.
3. Open **API development tools**.
4. Create an application.
5. Copy **api_id** and **api_hash**.

### 👤 3. Get Your `OWNER_ID`

Use a Telegram ID bot such as **@userinfobot**, then copy your numeric user ID. The owner can use protected bot commands such as `/set`, `/stats`, `/log`, and `/restart`.

### 🗄️ 4. Create MongoDB Databases

You need two database names. They may live in the same MongoDB cluster.

Example layout:

```text
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/dbStremio
mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/storage_1
```

In MongoDB Atlas:

1. Create a database user.
2. Add the server IP to Network Access. For hosted platforms with changing outbound addresses, `0.0.0.0/0` is commonly used, but restrict it whenever your deployment allows it.
3. Copy the Driver connection string.
4. Use URL-encoded credentials when the password contains special characters such as `@`, `:`, `/`, or `#`.

---

<a id="initial-configuration"></a>
## 🧩 Initial Configuration

Copy the sample file:

```bash
cp sample_config.env config.env
```

Fill only the startup values:

```env
# Telegram
API_ID="1234567"
API_HASH="your_telegram_api_hash"
BOT_TOKEN="1234567890:your_bot_token"
USER_SESSION_STRING=""
OWNER_ID="123456789"

# Database: exactly two URIs on first setup
DATABASE="mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/dbStremio,mongodb+srv://USER:PASSWORD@cluster.example.mongodb.net/storage_1"

# Server
PORT="8000"
```

### 📌 Required Startup Variables

| Variable | Required | Description |
|---|:---:|---|
| `API_ID` | Yes | Telegram application API ID. |
| `API_HASH` | Yes | Telegram application API hash. |
| `BOT_TOKEN` | Yes | Main Telegram bot token. |
| `OWNER_ID` | Yes | Numeric Telegram account ID for administrator-only bot commands. |
| `DATABASE` | Yes | Two comma-separated MongoDB connection URIs: tracking first, `storage_1` second. |
| `PORT` | Yes | Web server port. Use `7860` for Hugging Face Docker Spaces. |
| `USER_SESSION_STRING` | Optional | Required only for Global Search. Treat it like a password. |

### ⚠️ Important Configuration Rules

- ⚠️ Never publish `config.env`, session strings, MongoDB passwords, or bot tokens.
- ⚠️ Add `config.env` to `.gitignore`.
- ⚠️ Do not put your real secrets in `sample_config.env`.
- ⚠️ After the first start, configure the base URL, channels, TMDb key, and other runtime options from the dashboard.
- ⚠️ Change the default web login immediately after first sign-in.

---

<a id="deploy-with-docker-compose"></a>
## 🐳 Deploy with Docker Compose

Docker Compose is the simplest VPS deployment method.

```bash
git clone https://github.com/your-account/your-repository.git
cd your-repository
cp sample_config.env config.env
nano config.env
```

Start the application:

```bash
docker compose up -d --build
```

Useful commands:

```bash
# Follow application logs
docker compose logs -f

# Check running containers
docker compose ps

# Restart after changing startup-only configuration
docker compose restart

# Pull code changes and rebuild
git pull
docker compose up -d --build
```

The default Compose mapping is `8000:8000`. Open:

```text
http://YOUR_SERVER_IP:8000
```

> 🔒 **HTTPS required for best playback:** place the app behind HTTPS before using the URL as your final Stremio/Nuvio Base URL.

---

<a id="deploy-on-hugging-face-spaces"></a>
## 🤗 Deploy on Hugging Face Spaces

> 🌐 **Best for an easy public deployment:** Hugging Face Spaces builds this project as a Docker application and gives it a secure HTTPS address automatically. Your media and app data remain in Telegram and MongoDB; the Space only runs the bot, dashboard, and streaming API.

### 🗺️ Hugging Face Deployment Map

```text
🧑‍💻 Your GitHub / local project
          │
          ├── 📦 Upload project files to a Docker Space
          ├── 🔐 Add Telegram + MongoDB values as Space Secrets
          └── ▶️ Space builds and starts on port 7860
                         │
                         ▼
         🌐 https://YOUR-USERNAME-YOUR-SPACE.hf.space
                         │
                         ├── 🖥️ Dashboard settings
                         ├── 🤖 Telegram indexing and streaming
                         └── 📺 Stremio / Nuvio personal manifest URLs
```

### ✅ Before You Start

Prepare these first:

| You need | Why it is needed |
|---|---|
| 🤗 Hugging Face account | Creates and hosts the Docker Space. |
| 🤖 Telegram bot token | Connects the main bot. |
| 🔑 Telegram API ID + API hash | Connects the Telegram streaming client. |
| 👤 Owner ID | Restricts owner-only bot actions. |
| 🗄️ Two MongoDB URIs | Preserves media index, settings, subtitles, tokens, and catalog data outside the Space. |
| 🎬 TMDb API key | Added after first boot from the dashboard for better metadata matching. |
| 📁 This full project folder | Must include `Dockerfile`, `start.sh`, `Backend/`, `pyproject.toml`, `uv.lock`, assets, and the Space `README.md`. |

> 🚫 **Do not upload `config.env` to a Space.** Keep all secrets in Hugging Face **Secrets**. The project reads them as normal environment variables during startup.

### 🧱 1. Confirm the Space Card Metadata

Hugging Face reads the YAML block at the very top of the repository `README.md`. Keep this block at the top when you replace the README:

```yaml
---
title: TharinduHub Stremio
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
short_description: Telegram Stremio streaming with subtitle manager
---
```

| Field | Required value | Why it matters |
|---|---|---|
| `sdk` | `docker` | Tells Hugging Face to build the project with its `Dockerfile`. |
| `app_port` | `7860` | Makes the FastAPI service reachable through the Space URL. |
| `title` / `emoji` / colors | Your preferred branding | Controls the Space card appearance. |
| `short_description` | Short public summary | Appears in the Space listing. |

> ✅ This project already uses `PORT` from the environment. On Hugging Face, set `PORT=7860` so it matches `app_port: 7860`.

### 🆕 2. Create the Docker Space

1. Open **Hugging Face → New Space**.
2. Select your account or organization as the owner.
3. Choose a clear Space name, for example `stremio-tg`.
4. Select **Docker** as the SDK.
5. Select **Public** when Stremio or Nuvio users must access the Space directly.
6. Choose the available CPU hardware for testing, then create the Space.

> ⚠️ **Public is normally required for Stremio/Nuvio:** external add-on clients need to reach the direct `.hf.space` URL. Protect access through the app’s dashboard password, individual add-on tokens, subscriptions, and private Telegram channels—not by exposing credentials in a public repository.

> 💤 **Sleep behaviour:** free Hugging Face hardware may sleep after inactivity. While asleep, live indexing, background checks, and playback will not run until the Space wakes. Use an always-running paid hardware option when you need uninterrupted bot and streaming availability.

### 📤 3. Upload the Project — Browser Method

This is the simplest method on a phone or without Git.

1. 📦 Extract the project ZIP on your device or computer.
2. 🤗 Open your new Space → **Files and versions**.
3. ➕ Choose **Add file → Upload files**.
4. 📁 Upload the extracted project contents, preserving all folders:

```text
Backend/
assets/
Dockerfile
start.sh
pyproject.toml
uv.lock
requirements.txt
sample_config.env
docker-compose.yaml
README.md
```

5. 📝 Ensure the file is named exactly `README.md` in the Space root.
6. 🚫 Do **not** upload `.env`, `config.env`, `*.session`, `__pycache__`, logs, or private backup files.
7. 💾 Commit the upload from the browser. Hugging Face starts the Docker build automatically.

> 🔎 **Build check:** open **Logs** and wait for the Space status to become **Running**. The application log should show that the web server is listening on `0.0.0.0:7860` and that Telegram-Stremio started successfully.

### 🧑‍💻 4. Upload or Update — Git Method

Use this method for cleaner updates from a computer.

#### 🔐 Authenticate once

1. Create a Hugging Face **Write** access token from your account settings.
2. Install the Hugging Face CLI and sign in:

```bash
pip install -U "huggingface_hub[cli]"
hf auth login
```

3. Paste the Write token when requested. Never commit the token into a repository or paste it into the remote URL.

#### 🚀 Push the project

Run these commands inside the project folder:

```bash
git init
git branch -M main
git add -A
git commit -m "Deploy Stremio-TG to Hugging Face"
git remote add origin https://huggingface.co/spaces/YOUR_HF_USERNAME/YOUR_SPACE_NAME
git push -u origin main
```

For future updates:

```bash
git add -A
git commit -m "Update Stremio-TG"
git push
```

> 🛡️ **Authentication error?** Run `hf auth login` again with a new Write token, then retry `git push`. A Hugging Face access token is used as the Git password; your normal Hugging Face account password is not used for Git pushes.

### 🔐 5. Add Hugging Face Secrets and Variables

Open your Space → **Settings → Variables and secrets**.

#### 🔒 Add these as Secrets

| Secret name | Example / format | Required | Notes |
|---|---|:---:|---|
| `API_ID` | `12345678` | ✅ | Telegram API numeric ID from `my.telegram.org`. |
| `API_HASH` | `abc123...` | ✅ | Telegram application hash. |
| `BOT_TOKEN` | `123456:ABC...` | ✅ | Main bot token from @BotFather. |
| `OWNER_ID` | `123456789` | ✅ | Your numeric Telegram user ID. |
| `DATABASE` | `mongodb+srv://.../tracking,mongodb+srv://.../storage_1` | ✅ | Exactly two comma-separated MongoDB URIs on first boot. |
| `USER_SESSION_STRING` | Telegram session string | ⬜ | Needed only for Global Search / user-account fallback. |

#### ⚙️ Add this as a Variable

| Variable name | Value | Required | Notes |
|---|---|:---:|---|
| `PORT` | `7860` | ✅ | Must match the Space card `app_port: 7860`. |

> 🔐 **Secret safety:** values stored as Hugging Face Secrets are write-only in the Space settings. Put bot tokens, MongoDB URIs, Telegram session strings, and API hashes there—never in `README.md`, commits, screenshots, or public Variables.

> 🔄 **Restart behaviour:** changing a Secret, Variable, or hardware setting triggers a Space restart. Wait for the status to return to **Running** before testing.

### 🗄️ 6. MongoDB Setup for Spaces

Use two separate database names—these can be on the same MongoDB Atlas cluster.

```text
mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/tracking,
mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/storage_1
```

Paste the two URIs on **one line**, without a line break:

```text
mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/tracking,mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/storage_1
```

✅ MongoDB keeps your important state outside the Space:

- 🗄️ Indexed movies, shows, split files, and stream references.
- 💬 Subtitle records, matching status, and manual language corrections.
- 🖥️ Dashboard settings, catalog configuration, tokens, and subscriptions.
- 🔄 Scan state and other runtime data.

> 💾 Hugging Face container storage is temporary by default. Do not rely on the Space filesystem for sessions, uploads, databases, or backups. This project is designed to keep the long-lived library state in MongoDB and Telegram.

### ▶️ 7. First Successful Start

After the build becomes **Running**:

1. Open the **direct Space URL**, not only the Hugging Face repository page:

```text
https://YOUR_HF_USERNAME-YOUR_SPACE_NAME.hf.space
```

2. Sign in to the dashboard with the initial credentials:

```text
Username: admin
Password: admin
```

3. Open **Admin → Settings**.
4. Change the dashboard username and password immediately.
5. Set **Base URL** to the exact direct Space URL:

```text
https://YOUR_HF_USERNAME-YOUR_SPACE_NAME.hf.space
```

6. Add your **TMDb API key**.
7. Add the Telegram channel username or numeric ID under **Auth channels**.
8. Confirm the main bot is an administrator in every configured channel.
9. Enable **Replace Mode** if you want newer uploads to replace an existing same-quality stream.
10. Save Settings.
11. Open **Admin → Tools** and run the appropriate scan for existing files.
12. Create an access token, then install the generated manifest in Stremio or Nuvio.

> 📌 **Base URL rules:** use HTTPS, use the direct `.hf.space` address, and do not add a trailing `/`. A wrong Base URL can create broken stream, subtitle, and add-on links.

### 📺 8. Install the Add-on After Deployment

Your personal manifest URL has this format:

```text
https://YOUR_HF_USERNAME-YOUR_SPACE_NAME.hf.space/stremio/YOUR_TOKEN/manifest.json
```

1. 🔑 Create or retrieve a user token from **Admin → Access Management**.
2. 📋 Copy that user’s manifest URL.
3. 🎬 Paste it into Stremio’s add-on installation flow, or Nuvio’s add-on page.
4. 🔄 Refresh the catalog after installation.

> 🛡️ Each tokenized manifest URL is private. Give every user a different token and revoke one immediately if it is shared publicly.

### 🧪 9. Hugging Face Post-Deploy Checklist

| Check | Expected result |
|---|---|
| 🤗 Space status | **Running** |
| 📜 Space logs | Telegram client, MongoDB tracking DB, and storage DB connect successfully. |
| 🌐 Direct URL | Dashboard opens at `https://...hf.space`. |
| 🔐 Dashboard | Default login is changed to your private credentials. |
| ⚙️ Base URL | Exactly matches the direct Space URL. |
| 🤖 Telegram | Bot is admin in each source channel. |
| 🗄️ MongoDB | Two required connections show success in logs. |
| 🎬 Add-on | Tokenized `/stremio/TOKEN/manifest.json` returns successfully. |
| 💬 Subtitles | Existing unmatched records are relinked through **Subtitles → Match unmatched** after a matcher update. |

### 🩺 10. Hugging Face Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| 🧱 Build fails before startup | Missing project files or malformed `README.md` YAML | Ensure `Dockerfile`, `Backend/`, `start.sh`, `pyproject.toml`, `uv.lock`, and the YAML Space card are in the repository root. |
| 🚫 Space shows an error / 500 | Startup secret is missing or invalid | Check every required Secret, especially `DATABASE`, `BOT_TOKEN`, `API_ID`, and `API_HASH`. |
| 🌐 App opens but Stremio will not play | Base URL is wrong or Space is sleeping | Set the exact `.hf.space` URL, reinstall/update the manifest, and use a running Space. |
| 🔐 Git push says invalid username or password | Git has no valid Hugging Face authentication | Run `hf auth login` with a Write token and push again. |
| 🤖 Bot starts but does not index files | Bot is not an admin or channel is not saved | Add the bot as channel admin, save Auth channels in the dashboard, then run a scan. |
| 🗄️ MongoDB connection fails | Bad URI, unescaped password, or Atlas access rule | Test both URIs, URL-encode special password characters, and allow the Space to reach the cluster. |
| 💤 Bot stops after idle time | Space went to sleep | Open the Space to wake it, or select always-running paid hardware for continuous service. |
| 💬 Subtitle stays unmatched | Video not indexed yet or filename lacks safe title/episode data | Index the video first, then run **Match unmatched** or manually link it from Subtitles. |

### 🔄 11. Updating a Hugging Face Space Safely

1. 🗄️ Back up MongoDB before changing major database or parser code.
2. 💾 Keep a secure copy of your current Secrets list—never inside Git.
3. 📤 Push or upload the updated source files.
4. 🏗️ Watch **Build logs** until the Space returns to **Running**.
5. 🔎 Check MongoDB connections, dashboard access, Base URL, and a test token manifest.
6. 💬 Run **Match unmatched** after subtitle-parser updates.
7. 🧩 Run a targeted scan only if a new scanner feature needs it.

> ✅ **No reconfiguration normally required:** runtime dashboard settings persist in the tracking MongoDB database, so a normal source-code update or Space restart should not erase channel settings, tokens, subtitles, catalogs, or the media index.

---

<a id="deploy-on-a-vps-with-https"></a>
## 🛡️ Deploy on a VPS with HTTPS

A domain and reverse proxy provide the most stable playback URL.

### 🌐 1. Point Your Domain to the VPS

Create an A record:

| Type | Host | Value |
|---|---|---|
| `A` | `@` or a subdomain | Your VPS public IPv4 address |

### 🛡️ 2. Install Caddy

Install Caddy using its official repository instructions for your Linux distribution, then set a basic reverse-proxy configuration:

```caddy
your-domain.example {
    reverse_proxy 127.0.0.1:8000
}
```

Reload Caddy after saving the file.

### 🔗 3. Set the Dashboard Base URL

In **Admin → Settings**, set:

```text
https://your-domain.example
```

Do not include a trailing slash. This URL is used when generating add-on and delivery links.

---

<a id="first-run-dashboard-setup"></a>
## 🖥️ First-Run Dashboard Setup

Open the web dashboard, sign in, then visit **Admin → Settings**.

Initial credentials:

```text
Username: admin
Password: admin
```

> 🚨 **Change these immediately** before inviting anyone to use the service.

### ✅ Essential Settings

| Setting | Recommended value | Why it matters |
|---|---|---|
| Admin username / password | Your own secure credentials | Protects the dashboard. |
| Base URL | Your exact public HTTPS URL | Required for add-on, stream, and subtitle links. |
| TMDb API key | Your v3 key | Improves title matching and catalog metadata. |
| Auth channels | Your media channels | Defines where scans and live indexing operate. |
| Replace Mode | Enabled | Replaces an old stream with a new file of the same title/episode/quality. |
| Hide Catalog | Disabled for browsing; enabled for direct-library-only use | Controls public catalog availability in the add-on. |

### ➕ Optional Settings

| Setting | Use |
|---|---|
| Extra storage databases | Expand the library beyond the initial storage database. |
| Multi-token clients | Add additional Telegram bot tokens for more parallel streaming capacity. Each bot must be an admin in the media channels. |
| HTTP proxy URL | Route outbound metadata/API requests through an HTTP proxy. |
| Show proxied and direct links | Offer both stream styles when a proxy is configured. |
| Subscription | Enable subscription and payment flow. |
| Global Search | Search selected Telegram channels using the optional user-session client. |
| Upstream repository / branch | Source used by the owner-only restart/update workflow. |

Most runtime settings save to MongoDB and apply without rebuilding the container. Startup credentials and a newly added user session should be set before a restart.

---

<a id="add-stremio-or-nuvio"></a>
## 📺 Add Stremio or Nuvio

Each user should use a personal tokenized manifest URL:

```text
https://YOUR_DOMAIN/stremio/YOUR_TOKEN/manifest.json
```

### 🔑 Create or Retrieve a Token

- 🔑 Open **Admin → Access Management** and create/manage the user token.
- 🔑 In non-subscription mode, the owner can also send `/start` to the bot to receive an add-on link.
- 🔑 In subscription mode, the bot supplies a token after the user is approved.

### 🎬 Install in Stremio

1. Open Stremio.
2. Use the add-on installation flow.
3. Paste the full personal manifest URL.
4. Install or update the add-on.

### 📺 Install in Nuvio

1. Open Nuvio.
2. Go to the add-on section.
3. Paste the same full personal manifest URL.
4. Install it, then refresh the catalog if needed.

> 🔐 **Treat this link like a password.** Do not share a tokenized manifest URL publicly. Revoke the token from Access Management if it is exposed.

---

<a id="upload-and-naming-guide"></a>
## 📤 Upload & Naming Guide

The matcher accepts many real-world filenames, but a clean file name produces faster and more accurate metadata.

### 🎞️ Movies

Recommended pattern:

```text
Title (Year) 1080p WEB-DL x264 AAC.mkv
```

Example:

```text
Saiyaara (2025) 720p NF WEB-DL AAC 5.1 HEVC.mkv
```

Include:

- 🎞️ Title
- 🎞️ Year
- 🎞️ Resolution or quality when available

The source, codec, audio tags, and release group are optional.

### 📺 TV Episodes

Recommended pattern:

```text
Series Name S01E04 1080p WEB-DL DDP5.1.mkv
```

Examples:

```text
Hell's Paradise S01E01 1080p WEBRip 10bit.mkv
Series Name 1x04 720p WEB-DL.mkv
```

Use `S01E01` whenever possible. The parser also recognizes `1x01` and textual season/episode patterns.

### 🛠️ Manual Metadata Override

When a file resolves to the wrong movie or show:

1. Open the media item in **Media Management**.
2. Choose **Edit**.
3. Use metadata search and apply the correct result.

For an upload batch, the owner can use:

```text
/set https://www.imdb.com/title/tt1234567/
```

Forward the related files, then clear the temporary override:

```text
/set
```

The command accepts an IMDb or TMDb URL.

---

<a id="subtitle-system"></a>
## 💬 Subtitle System

### 📄 Supported Formats

| Extension | Supported |
|---|:---:|
| `.srt` | Yes |
| `.vtt` | Yes |
| `.ass` | Yes |
| `.ssa` | Yes |
| `.sub` | Yes |
| `.smi` / `.sami` | Yes |

Subtitle documents can be indexed during a channel scan or when they arrive in a configured media channel.

### 🌍 Language Detection

The parser checks the subtitle caption and filename for a supported language name, alias, or credible release-language code.

Examples that remain explicitly detected:

```text
Movie.2025.Sinhala.srt                 → Sinhala (si)
Movie.2025.720p.si.WEB-DL.srt          → Sinhala (si)
Movie.2025.English.srt                 → English (en)
Anime.S01E01.Japanese.Sub.srt          → Japanese (ja)
Film.2025.Arabic.srt                   → Arabic (ar)
```

### 🇱🇰 Sinhala Default Behaviour

When the filename and caption contain **no recognized supported language**, the subtitle defaults to **Sinhala (`si`)**.

```text
Movie Title 2025.srt                   → Sinhala (si)
```

An explicit language always has priority. A filename that clearly says `English`, `Japanese`, `Arabic`, `Tamil`, `Hindi`, and similar languages will not be changed to Sinhala.

### 🧬 Subtitle Matching Order

The service applies the safest match first:

1. Explicit subtitle tag with IMDb or TMDb ID.
2. Embedded IMDb/TMDb ID in the caption or filename.
3. Local movie/series matching by normalized title, year, season, and episode.
4. Metadata alias lookup for translated, romanized, or alternate names.
5. Unmatched queue for manual correction or a later relink.

### 📝 Best Subtitle Naming Patterns

Movie subtitle:

```text
Movie Title (2025) Sinhala.srt
Movie.Title.2025.720p.si.WEB-DL.srt
```

Episode subtitle:

```text
Series Name S01E02 Sinhala.srt
Series_Name_S01E02_JAPANESE_1080p.srt
```

### 🏷️ Guaranteed Manual Link Tag

Use an explicit ID when a subtitle has a difficult title:

```text
[SUB:tt1234567 si]
```

For an episode:

```text
[SUB:tt1234567 S01E02 Sinhala]
```

Place this in the Telegram caption or subtitle filename. The ID removes title ambiguity and the season/episode marker limits the subtitle to the correct episode.

### 🔄 Fix Old Unmatched Subtitles

After improving filenames, indexing media later, or deploying a newer subtitle matcher:

1. Open **Subtitles** in the dashboard.
2. Filter by **Unmatched** if necessary.
3. Press **Match unmatched**.

Relinking reparses stored subtitle names, refreshes the language where required, and attempts local plus metadata-alias matching again. It does not delete the subtitle document.

---

<a id="split-files-and-archive-volumes"></a>
## 🧩 Split Files & Archive Volumes

The scanner recognizes supported multipart sources, including common numbered archive/upload parts such as `.zip.001`, `.zip.002`, and compatible split video uploads.

When all required parts are available, Stremio-TG stores one virtual media record with part references and presents it as a single stream. It does not show every part as a separate movie or episode.

### ✅ Recommendations

- ✅ Keep all parts in the same indexed channel.
- ✅ Use consecutive numbered parts with the same base filename.
- ✅ Upload every required volume before expecting playback.
- ✅ Avoid unrelated files with the same base name between split parts.
- ✅ Do not rename only one part after upload.

The scanner validates split candidates conservatively so ordinary filenames such as `1080p`, `720p`, or other numbers are not incorrectly treated as split parts.

---

<a id="scanning-matching-and-catalog-tools"></a>
## 🔍 Scanning, Matching & Catalog Tools

### 🔍 Channel Scans

Open **Admin → Tools** to start a scan.

| Scope | What it does |
|---|---|
| Media | Indexes or refreshes movies, series, episodes, and compatible split uploads. |
| Subtitles | Indexes subtitle documents without clearing media records. |
| Full | Processes media and subtitles together, then runs final subtitle relinking. |

The scan state tracks progress and supports resume behavior. A full scan keeps its subtitle status accurate even when a subtitle is indexed before its matching video appears later in the same channel.

### ♻️ When to Scan Again

Run the appropriate scope after:

- ♻️ Adding an existing channel to settings.
- ♻️ Migrating a library to a new database.
- ♻️ Renaming old Telegram captions.
- ♻️ Deploying improved subtitle or split-file detection.
- ♻️ Fixing incorrectly matched media in bulk.

### 🗃️ Catalogs

The catalog page supports:

- 🗃️ Custom catalogs.
- 🗃️ Adding or removing media from a catalog.
- 🗃️ Auto-sync settings and status.
- 🗃️ Metadata-driven collections.

Automatic catalog synchronization uses the configured metadata key and can skip records that are already classified. A log such as `scanned: 29, skipped: 29, classified: 0` is normal when all scanned entries already have the needed catalog data.

### 🔗 Dead Links

The background dead-link checker verifies stored Telegram sources. Use dashboard tools to inspect or purge dead entries when a source message has been deleted or is no longer accessible.

---

<a id="access-tokens-and-subscriptions"></a>
## 🔐 Access Tokens & Subscriptions

### 🔑 Access Tokens

Every installed add-on uses a token. From **Admin → Access Management**, you can:

- 🔑 Create a token.
- 🔑 View active and expired tokens.
- 🔑 Assign or extend access.
- 🔑 Revoke access.
- 🔑 Delete a token.
- 🔑 Link an older token to a Telegram user ID.
- 🔑 Configure limits where available.

Use a separate token for each person. Revoke a token immediately if a manifest URL is shared accidentally.

### 💳 Optional Subscriptions

Enable subscriptions in **Admin → Settings** only when you need paid or managed access.

Configure:

- 💳 Subscription toggle.
- 💳 Subscription group ID.
- 💳 Subscription/group URL.
- 💳 Approver Telegram IDs.
- 💳 Payment instructions.
- 💳 Optional payment QR image URL.

Then create plans from **Admin → Subscription Management**.

User flow:

```text
/start
  → select plan
  → receive payment instructions
  → send payment screenshot
  → approver accepts or rejects
  → user receives personal Stremio add-on link
```

When subscriptions are active, the add-on verifies token ownership, subscription status, expiry, and configured group membership before returning streams.

---

<a id="global-search"></a>
## 🌐 Global Search

Global Search can search selected Telegram channels that are not already fully indexed in the local catalog.

#<a id="requirements"></a>
## 🧰 Requirements

- 🧰 A valid `USER_SESSION_STRING` in startup configuration.
- 🧰 A restart after adding or replacing the session string.
- 🧰 Global Search enabled from **Admin → Settings**.
- 🧰 Valid numeric Telegram channel IDs in the Global Search channel list.

The user session belongs to a real Telegram account. Protect it as carefully as a password:

- 🧰 Never place it in GitHub.
- 🧰 Never send it to another person.
- 🧰 Revoke the session from Telegram **Settings → Devices** if exposed.

Global Search results are filtered by title/episode relevance and can return up to the configured limits from selected channels.

---

<a id="bot-commands"></a>
## 🤖 Bot Commands

| Command | Access | Purpose |
|---|---|---|
| `/start` | Owner in standard mode; users in subscription mode | Provides the available add-on access flow. |
| `/set <IMDb-or-TMDb-URL>` | Owner | Sets a temporary metadata override for files uploaded next. |
| `/set` | Owner | Clears the temporary metadata override. |
| `/stats` | Owner | Sends database, stream, channel, and uptime statistics. |
| `/log` | Owner | Sends the current log file. |
| `/restart` | Owner | Runs the configured restart/update workflow. |
| `/status` | Subscription mode | Shows subscription status and expiry. |

> ✅ **Normal startup behaviour:** the bot refreshes its command list on boot. A log showing that existing commands were deleted and re-created is expected.

---

<a id="dashboard-pages"></a>
## 🖥️ Dashboard Pages

| Page | Purpose |
|---|---|
| `/` | Main dashboard, service status, stream statistics, and shortcuts. |
| `/admin/dashboard` | Administrative overview and system health. |
| `/media/manage` | Browse, edit, rescan, and remove movies or TV entries. |
| `/subtitles` | Search, filter, edit, relink, manually match, or delete subtitles. |
| `/catalogs` | Create and manage custom catalogs and automatic catalog sync. |
| `/admin/access` | Manage tokens, users, limits, access dates, and revocation. |
| `/admin/subscriptions` | Create plans and manage subscription users. |
| `/admin/settings` | Save runtime settings. |
| `/admin/tools` | Run channel scans, database checks, and dead-link maintenance. |
| `/status` | Public status page. |
| `/stremio` | Add-on installation guidance page. |

> 🔐 **Expected security behaviour:** dashboard API calls redirect to `/login` when you are signed out. A `302 Found` for `/api/system/stats` means authentication is protecting the endpoint; it is not an application crash.

---

<a id="troubleshooting"></a>
## 🩺 Troubleshooting

### 🔐 The Dashboard Redirects to `/login`

A `302 Found` response from a protected endpoint is normal when the browser has no valid dashboard session. Sign in again and reload the page.

### ✅ The Manifest Ping Reports `Status: 200`

This is healthy. The background pinger is confirming the add-on manifest is reachable.

### 🧠 Metadata Is Wrong or Missing

1. Confirm a TMDb API key and Base URL are set in dashboard settings.
2. Use **Media Management → Edit → metadata search**.
3. For a related upload batch, use `/set` with the correct IMDb or TMDb URL before forwarding files.
4. Ensure the filename includes a clean title and release year.

### 💬 A Subtitle Is Indexed but Unmatched

This does not mean the file was lost. It means no safe media target was found at that time.

- 💬 Confirm the matching movie or episode is indexed.
- 💬 Ensure movie title/year or series `SxxEyy` information is present.
- 💬 Add a `[SUB:tt…]` tag for guaranteed matching.
- 💬 Open **Subtitles → Match unmatched** after the video is available.

### 🌍 A Subtitle Shows the Wrong Language

- 🌍 Put the full language name in the filename or caption, for example `Sinhala`, `English`, `Arabic`, or `Japanese`.
- 🌍 Use a credible release code such as `.si.WEB-DL` rather than an ambiguous final uploader suffix.
- 🌍 Edit the subtitle from the dashboard if the original document needs a manual correction.

> 🇱🇰 **Sinhala fallback:** unlabelled subtitles default to Sinhala by design. Explicitly detected languages remain unchanged.

### 🤖 The Bot Does Not Index Channel Files

- 🤖 Confirm the channel is listed in **Auth channels**.
- 🤖 Confirm the bot is an administrator in that channel.
- 🤖 Verify the bot can view the media messages.
- 🤖 Run a Media, Subtitle, or Full scan from **Admin → Tools**.
- 🤖 Check `/log` as owner for the exact parse or Telegram error.

### 🧩 A Split File Does Not Appear as One Stream

- 🧩 Confirm every part was uploaded.
- 🧩 Use consistent filenames such as `Movie.mkv.zip.001`, `Movie.mkv.zip.002`.
- 🧩 Keep the parts in the same indexed channel.
- 🧩 Run a Media or Full scan after all parts are present.

### 🚫 `Invalid or expired API token`

The add-on URL does not contain a valid active token. Generate a new token from **Access Management**, install the new manifest URL, and revoke the exposed/old token if appropriate.

### 🌐 Global Search Is Unavailable

- 🌐 Confirm `USER_SESSION_STRING` is set before start.
- 🌐 Restart the application.
- 🌐 Enable Global Search in runtime settings.
- 🌐 Add valid numeric channel IDs.
- 🌐 Check that the Telegram user session is still active and not revoked.

### 🗄️ MongoDB Connection Fails

- 🗄️ Verify both URI values are valid and comma-separated with no accidental extra commas.
- 🗄️ URL-encode password special characters.
- 🗄️ Check Atlas database-user permissions.
- 🗄️ Check Atlas Network Access rules.

---

<a id="security-checklist"></a>
## 🔒 Security Checklist

Before giving anyone access:

- [ ] Change the dashboard `admin / admin` credentials.
- [ ] Keep `config.env` outside Git history.
- [ ] Store platform credentials as secrets, not visible environment variables.
- [ ] Use a strong MongoDB password and least-privilege database user.
- [ ] Use HTTPS for the Base URL.
- [ ] For Stremio/Nuvio playback, use a public Space only with app-level token protection; use private channels and keep all credentials in Secrets.
- [ ] Give every user a separate add-on token.
- [ ] Revoke leaked tokens from Access Management.
- [ ] Protect `USER_SESSION_STRING` like a Telegram account password.
- [ ] Keep Telegram channels private unless you intentionally want public access.
- [ ] Back up MongoDB before large scans, bulk cleanup, or database changes.

---

<a id="project-layout"></a>
## 🗂️ Project Layout

```text
.
├── Backend/
│   ├── fastapi/                 # Dashboard, API routes, Stremio routes, static assets
│   ├── helper/                  # Metadata, scans, subtitles, catalogs, DB, split files
│   ├── pyrofork/                # Telegram bot clients and command plugins
│   ├── config.py                # Startup environment reader
│   └── __main__.py              # Service startup
├── assets/                      # Branding assets
├── Dockerfile                   # Docker image definition
├── docker-compose.yaml          # Docker Compose deployment
├── sample_config.env            # Startup configuration template
├── start.sh                     # Container start command
├── pyproject.toml               # Python project dependencies
└── README.md                    # This guide
```

---

<a id="updating-safely"></a>
## 🔄 Updating Safely

1. Back up the tracking and storage databases.
2. Save a copy of `config.env` or your platform secrets list.
3. Pull the new code.
4. Rebuild/restart the deployment.
5. Open the dashboard and confirm the settings revision, channels, base URL, and token access.
6. Run **Match unmatched** after a subtitle matcher update.
7. Run a targeted scan only when needed; avoid unnecessary destructive reindex operations.

For Docker Compose:

```bash
git pull
docker compose up -d --build
docker compose logs -f
```

---

<a id="credits"></a>
## 💙 Credits & Upstream Project

<div align="center">

### ✨ Built with respect for the original project

<a href="https://github.com/weebzone/Telegram-Stremio">
  <img src="https://img.shields.io/badge/%F0%9F%92%99%20Forked%20from-weebzone%2FTelegram--Stremio-0D1117?style=for-the-badge&logo=github&logoColor=white" alt="Forked from weebzone/Telegram-Stremio" />
</a>

<br />
<br />

> 💙 **Forked from [weebzone/Telegram-Stremio](https://github.com/weebzone/Telegram-Stremio)**  
> Original project foundation by **Weebzone** — thoughtfully customized and maintained by [**tharindu899**](https://github.com/tharindu899).

</div>

<br />

| 🌟 Project / Service | 🎯 Contribution |
|---|---|
| [💙 Weebzone / Telegram-Stremio](https://github.com/weebzone/Telegram-Stremio) | Original Telegram-to-Stremio project foundation. |
| [🎬 Stremio](https://www.stremio.com/) | Add-on ecosystem and media client platform. |
| [⚡ FastAPI](https://fastapi.tiangolo.com/) | API and dashboard service framework. |
| [🍃 MongoDB](https://www.mongodb.com/) | Metadata, settings, token, subtitle, and catalog storage. |
| [🤗 Hugging Face Spaces](https://huggingface.co/spaces) | Docker deployment platform. |
| [✨ tharindu899](https://github.com/tharindu899) | Custom branding, UI, subtitle workflow, and deployment documentation. |

> 🤝 **Upstream respect:** Keep the original license and this credit when sharing your fork. Check upstream changes before merging future updates, while keeping your custom features independent.

---

<a id="license"></a>
## 📜 License

📜 This project is distributed under the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE) for the full license text.

---

<p align="center">
  <strong>🎬 TharinduHub • Stremio-TG</strong><br />
  <sub>Built with ❤️ for a clean private Telegram library experience</sub><br />
  <sub>💙 Forked from <a href="https://github.com/weebzone/Telegram-Stremio">weebzone/Telegram-Stremio</a> · Customized by <a href="https://github.com/tharindu899">tharindu899</a></sub>
</p>
