---
title: TG Stremio
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---

<p align="center">
  <img src="https://i.ibb.co/wNdM9vBB/banner-v7.png" alt="TG Stremio Banner" width="900"/>
</p>


<p align="center">
  A powerful, self-hosted <b>Telegram Stremio Media Server</b> built with <b>FastAPI</b>, <b>MongoDB</b>, and <b>PyroFork</b> — seamlessly integrated with <b>Stremio</b> for automated media streaming and discovery.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/UV%20Package%20Manager-2B7A77?logo=uv&logoColor=white" alt="UV Package Manager" />
  <img src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/PyroFork-EE3A3A?logo=python&logoColor=white" alt="PyroFork" />
  <img src="https://img.shields.io/badge/Stremio-8D3DAF?logo=stremio&logoColor=white" alt="Stremio" />
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <a href="https://github.com/tharindu899/Stremio-TG"><img src="https://img.shields.io/badge/Fork-tharindu899-181717?logo=github&logoColor=white" alt="Fork by tharindu899" /></a>
  <a href="https://t.me/TharinduHub"><img src="https://img.shields.io/badge/Telegram-TharinduHub-2CA5E0?logo=telegram&logoColor=white" alt="TharinduHub" /></a>
</p>

---

## 🧭 Quick Navigation

* [🚀 Introduction](#-introduction)
  * [✨ Key Features](#-key-features)
  * [💳 Subscription Management](#-subscription-management)
  * [📋 Subscription Plans](#-subscription-plans)
  * [🤖 Bot Payment Flow](#-bot-payment-flow)
  * [🗃️ Access Management](#️-access-management)
  * [🎬 Stremio Addon Integration](#-stremio-addon-integration)

* [⚙️ How It Works](#️-how-it-works)
  * [📖 Overview](#overview)
  * [📤 Upload Guidelines](#upload-guidelines)
  * [🧹 Automatic Caption Formatting](#-automatic-caption-formatting)
  * [🎬 OVA & Special Episodes](#-ova--special-episodes-season-0)
  * [🔁 Quality Replacement Logic](#-quality-replacement-logic)
  * [🎥 Updating CAMRip or Low-Quality Files](#-updating-camrip-or-low-quality-files)
  * [🏷️ Fixing Incorrect Metadata](#️-fixing-incorrect-metadata-manual-override)
  * [🎞️ Subtitle Support](#️-subtitle-support)
  * [📩 Owner-PM Upload Status](#-owner-pm-upload-status)
  * [⚙️ Behind the Scenes](#behind-the-scenes)

* [🖥️ Web Panel](#️-web-panel)

* [🤖 Bot Commands](#-bot-commands)
  * [📜 Command List](#command-list)
  * [⚙️ /set Command Usage](#set-command-usage)

* [🔧 Configuration Guide](#-configuration-guide)
  * [🪜 Step 1: Create Your config.env File](#-step-1-create-your-configenv-file)
  * [🔑 Step 2: How to Get Each Value](#-step-2-how-to-get-each-value)
  * [📱 Step 3: Generate Your Telegram Session String](#-step-3-generate-your-telegram-session-string)
  * [🧩 Step 4: Configure Everything Else (Web Settings Page)](#-step-4-configure-everything-else-web-settings-page)

* [🚀 Deployment Guide](#-deployment-guide)
  * [✅ Recommended Prerequisites](#-recommended-prerequisites)
  * [🐙 Heroku Guide](#-heroku-guide)
  * [🤗 Hugging Face Spaces Guide](#-hugging-face-spaces-guide)
  * [🐳 VPS Guide (Recommended)](#-vps-guide)

* [📺 Setting Up Your App (Nuvio Recommended)](#-setting-up-your-app-nuvio-recommended)
  * [📥 Install Nuvio](#-step-1-install-nuvio)
  * [🌐 Add the Addon](#-step-2-add-the-addon)

* [🏅 Contributors](#-contributors)


# 🚀 Introduction

This project is a **next-generation Telegram Stremio Media Server** that allows you to **stream your Telegram files directly through Stremio**, without any third-party dependencies or file expiration issues. It's designed for **speed, scalability, and reliability**, making it ideal for both personal and community-based media hosting.


> **Current custom build:** Hugging Face port `8000`, OVA/Special `S00E01` support, automatic bold filename captions, advertisement-text cleanup, raw/split-ZIP streaming, TMDb/BASE_URL environment repair, and Userbot-first Replace Mode deletion.


## ✨ Key Features

- ⚙️ **Multiple MongoDB Database Support**
- 📡 **Multiple Telegram Channel Support**
- ⚡ **Ultra-Fast Streaming Experience**
- 🔑 **Multi-Token Load Balancer**
- 🎬 **IMDb & TMDb Metadata Integration**
- 🎭 **OVA / Special Episode Support** — season-zero filenames such as `S00E01` stay in Season 0
- 🧹 **Automatic Caption Cleanup** — keeps the first supported filename, removes advertisement text, and formats it in bold
- 📄 **Filename Caption Fallback** — uploads with no caption automatically receive their Telegram filename
- 🧩 **Seamless Split File Streaming Support**
- 🎞️ **Play Multi-Part Videos as a Single Stream**
- ♾️ **Permanent Streaming Links (No Expiration)**
- 🧠 **Powerful Admin Dashboard**
- 💳 **Subscription & Premium Management**
- 🔐 **Advanced Access Control System**
- 📚 **Custom & Automatic Catalog Generation**
- 🌐 **Built-in Addon Proxy Support**
- 🔍 **Global Search Across Selected Channels**
- 👤 **Userbot-First Replace Deletion** — uses `USER_SESSION_STRING` first, then falls back to the bot
- 🔤 **Subtitle Indexing & Stremio Subtitle Resource**
- 📩 **Owner-PM Upload Status** — compact file processing status sent privately to the configured owner
- 🛠️ **Tools Page** — channel scan, DB integrity check, dead-link purge, speed test
- 📊 **Stream Analytics Dashboard**
- 🌍 **Public Server Status Page**
- 📱 **PWA Support** (installable web panel)



## ⚙️ How It Works

This project acts as a **bridge between Telegram storage and Stremio streaming**, connecting **Telegram**, **FastAPI**, and **Stremio** to enable seamless movie and TV show streaming directly from Telegram files.

### Overview

When you **forward Telegram files** (movies or TV episodes) to your **AUTH CHANNEL**, the bot automatically:

1. 🗃️ **Stores** the `message_id` and `chat_id` in the database.
2. 🧠 **Processes** file captions to extract key metadata (title, year, quality, etc.).
3. 🌐 **Generates a streaming URL** through the **PyroFork** module — routed by **FastAPI**.
4. 🎞️ **Provides Stremio Addon APIs**:
    - `/catalog` → Lists available media
    - `/meta` → Shows detailed information for each item
    - `/stream` → Streams the file directly via Telegram
    - `/subtitles` → Serves indexed subtitle files


### Upload Guidelines

For the best metadata match, use a clear media filename in the Telegram caption or document filename. The bot reads the caption first and falls back to the real Telegram filename when needed.

#### 🎥 For Movies

**Example Caption:**

```
Ghosted 2023 720p 10bit WEBRip [Org APTV Hindi AAC 2.0CH + English 6CH] x265 HEVC Msub ~ PSA.mkv
```

**Required Fields:**

- 🎞️ **Name** – Movie title (e.g., _Ghosted_)
- 📅 **Year** – Release year (e.g., _2023_)
- 📺 **Quality** – Resolution or quality (e.g., _720p_, _1080p_, _2160p_)

✅ **Optional:** Include codec, audio format, or source (e.g., `WEBRip`, `x265`, `Dual Audio`).

#### 📺 For TV Shows

**Example Caption:**

```
Harikatha.Sambhavami.Yuge.Yuge.S01E04.Dark.Hours.1080p.WEB-DL.DUAL.DDP5.1.Atmos.H.264-Spidey.mkv
```

**Required Fields:**

- 🎞️ **Name** – TV show title (e.g., _Harikatha Sambhavami Yuge Yuge_)
- 📆 **Season Number** – Use `S` followed by two digits (e.g., `S01`)
- 🎬 **Episode Number** – Use `E` followed by two digits (e.g., `E04`)
- 📺 **Quality** – Resolution or quality (e.g., _1080p_, _720p_)

✅ **Optional:** Include episode title, codec, or audio details (e.g., `WEB-DL`, `DDP5.1`, `Dual Audio`).


### 🧹 Automatic Caption Formatting

For every supported media or subtitle upload, the bot looks for the **first supported filename** in the caption. Everything after the detected extension is ignored, so channel advertisements, donation messages, and unrelated notes do not enter metadata parsing.

**Incoming caption:**

```text
Toukutsu Ou  - 01 [SLAnimebay][1080p x265].mkv

🛑 Please support us to keep this service alive by making a small donation
@AnimebaySL

Toukutsu Ou  - 01 [SLAnimebay][1080p x265].mkv
```

**Caption saved by the bot:**

```html
<b>Toukutsu Ou  - 01 [SLAnimebay][1080p x265].mkv</b>
```

Caption rules:

- If the caption contains a supported filename, only that first filename is kept and displayed in **bold**.
- If the upload has **no caption**, the real Telegram document filename is added in **bold**.
- If a non-empty custom caption contains no supported filename, the bot leaves that custom caption unchanged.
- HTML-sensitive characters in filenames are escaped safely before Telegram caption editing.
- The same caption-first → filename-fallback logic is used for live uploads and channel rescans.

**Supported video extensions:**

```text
.mkv .mp4 .avi .ts .m4v .mov .wmv .webm .flv .mpeg .mpg
```

**Supported subtitle extensions:**

```text
.srt .vtt .ass .ssa .sub .smi .sami
```

**Supported split examples:**

```text
Movie.2026.1080p.mkv.001
Movie.2026.1080p.mkv.zip.001
Movie.2026.1080p.mkv.z01
Movie.2026.1080p.zip.001
```

> Metadata override links/tags already present in the original caption are still available to the internal metadata workflow where applicable, while the visible caption is normalized to the filename.

---

### 🎬 OVA & Special Episodes (Season 0)

OVA, special, extra, bonus, and recap episodes can be uploaded using normal Stremio season-zero notation:

```text
Demon Slayer S00E01 1080p WEB-DL.mkv
Attack on Titan (2013) S00E01 1080p WEB-DL.mkv
```

The parser preserves `season_number = 0`, so these files are indexed as **Season 0 / Specials** instead of being converted to Season 1 or treated as movies.

Recommended format:

```text
Show Name S00E01 Quality Source.ext
```

- `S00` = Season 0 / Specials / OVA
- `E01` = Special episode number
- Resolution is recommended but not mandatory; files without a detected resolution are indexed with **Unknown** quality.

---


### 🔁 Quality Replacement Logic

> Works only when **Replace Mode** is enabled.

If a newly uploaded file has the same quality label (`720p`, `1080p`, `4K`, etc.) as an existing file, the bot automatically replaces the older entry with the new one.

**Example:** Uploading a new `Ghosted (2023) 720p` file will replace the existing `720p` version in the catalog.

This prevents duplicate quality entries and ensures only the latest version is available for streaming.

#### Delete client priority

When `USER_SESSION_STRING` is configured and the user session is usable, Replace Mode deletes older Telegram source messages in this order:

1. **Userbot first** — the authenticated user session attempts the deletion.
2. **Stream Bot fallback** — used only when the Userbot is unavailable or the Userbot deletion fails.

Without a usable `USER_SESSION_STRING`, the Stream Bot handles deletions directly. This avoids unnecessary `MESSAGE_DELETE_FORBIDDEN` warnings in channels where the user account can delete older posts but the bot cannot delete messages it did not create.

---

### 🆙 Updating CAMRip or Low-Quality Files

> Works only when **Replace Mode** is enabled.

If you initially uploaded a **CAMRip or low-quality version**, you can easily replace it with a better one:

1. Forward the **new, higher-quality file** (e.g., `1080p`, `WEB-DL`) to your **AUTH CHANNEL**.
2. The bot will **automatically detect and replace** the old CAMRip file in the database.
3. The Stremio addon will then **update automatically**, showing the new stream source.

✅ No manual deletion or command is needed — forwarding the updated file is enough!

---

### 🏷️ Fixing Incorrect Metadata (Manual Override)

If the addon identifies a movie or TV show incorrectly, or if metadata is missing altogether, you can easily correct it using one of the following methods:

#### Method 1: IMDb / TMDb URL Override

1. Copy the correct **IMDb** or **TMDb** URL for the movie or TV show.
2. Edit the message caption in your Telegram **AUTH CHANNEL** and paste the URL anywhere in the caption.
3. The bot will automatically:
   - Remove the existing metadata entry associated with that file.
   - Re-scan the provided URL.
   - Fetch and save the correct metadata.

#### Method 2: Scan Metadata from the Web Panel

1. Open the media entry from the Movies or TV Shows section.
2. Click **Edit**.
3. Select **Scan Metadata**.
4. Search for the correct title and choose the matching result.
5. Apply the changes.

✅ The addon will update the metadata instantly and refresh the catalog entry.

---

### 🎞️ Subtitle Support

The bot automatically indexes subtitle files (`.srt`, `.vtt`, `.ass`, `.ssa`, `.sub`) forwarded to AUTH channels alongside their corresponding media.

- **Auto-detection**: When a document with a subtitle extension is forwarded, it is indexed automatically.
- **Language detection**: Language is parsed from the filename or caption. Unrecognised files default to Sinhala (`si`).
- **Stremio integration**: Subtitles are served via the `/stremio/{token}/subtitles/` resource so any Stremio-compatible client can fetch them automatically.
- **Subtitle management**: The **Subtitles** page in the web panel lets you view, search, relink unmatched subtitles, and manage them manually.

---

### 📩 Owner-PM Upload Status

After a video, split-file part, subtitle, or unsupported document is processed, the bot can send a one-line status **only to the configured `OWNER_ID` in the bot private chat**.

- Nothing is posted or replied to in the source media channel.
- The message always uses the original Telegram **file name** — not the caption or matched title.
- It uses a background queue, so indexing and metadata matching do not wait for the Telegram PM.
- Normal upload results are not written as server log lines for this feature.

**Status format:**

```text
✅ Video : filename.mkv
✅ Split : filename.zip.001
✅ Subtitle : filename.srt
⚠️ Sub pending : filename.srt
❌ Metadata/index : filename.mkv
⏭️ skipped : filename.txt
```

**Setup:**

1. Set your numeric Telegram user ID as `OWNER_ID` in `config.env`.
2. Open the bot once from that owner account and press **Start**, so Telegram allows the bot to send private messages.
3. In the Web Panel, open **Settings → Library behavior** and keep **Upload status messages** enabled. It is enabled by default.

> During a large batch, PMs can arrive slightly after the file is processed because they are delivered in order at a safe rate. File indexing continues normally.

---

### Behind The Scenes

Here's how each component interacts:

| Component | Role |
| :--- | :--- |
| **Telegram Bot** | Handles uploads, forwards, file tracking, and subscription payments. |
| **MongoDB** | Stores message IDs, chat IDs, metadata, subtitles, tokens, and settings. |
| **PyroFork** | Generates Telegram-based streaming URLs via multi-client load balancing. |
| **FastAPI** | Hosts REST endpoints for streaming, catalog, metadata, and subtitles. |
| **Stremio Addon** | Consumes FastAPI endpoints for catalog display, playback, and subtitles. |

📦 **Flow Summary:**

```
Telegram ➜ MongoDB ➜ FastAPI ➜ Stremio ➜ User Stream
```


---


# 🖥️ Web Panel

The web panel is a **PWA** (installable on mobile/desktop) served at your deployment URL. It provides full admin control without touching config files or restarting the server.

| Page | URL | Description |
| :--- | :--- | :--- |
| **Login** | `/login` | Admin authentication |
| **Dashboard** | `/` | Overview of movies, TV shows, episodes, uptime, and storage |
| **Media Library** | `/media/manage` | Browse, search, and manage all indexed media |
| **Media Edit** | `/media/edit` | Edit metadata, quality entries, rescan from TMDb |
| **Subtitles** | `/subtitles` | View, relink, and manage indexed subtitle files |
| **Custom Catalogs** | `/catalogs` | Create and manage custom curated playlists for Stremio |
| **Subscriptions** | `/admin/subscriptions` | Manage subscription plans |
| **Access Management** | `/admin/access` | View and manage user addon tokens |
| **Settings** | `/admin/settings` | All runtime settings — no restart needed |
| **Tools** | `/admin/tools` | Channel scan, DB integrity check, dead-link detection & purge, stream analytics |
| **Admin Dashboard** | `/admin/dashboard` | System stats, dead links report, cache controls |
| **Public Status** | `/status` | Public-facing server status page |
| **Stremio Guide** | `/stremio` | Installation guide page for end users |

### 🛠️ Tools Page

The **Tools** page consolidates all maintenance operations:

- **Channel Scan** — Scans an AUTH channel's message history and indexes any missing media files into the database.
- **DB Check** — Verifies database integrity by checking that every stream entry still resolves to an accessible Telegram message.
- **Dead Link Detection** — Runs automatically every 24 hours; detects streams whose underlying Telegram messages are no longer reachable.
- **Dead Link Purge** — Removes confirmed dead stream entries from the database in bulk.
- **Speed Test** — Tests actual download throughput per Telegram client for a selected stream.
- **Stream Analytics** — Shows per-stream access history (last 200 records); can be cleared from here.

### 📊 Auto-Catalog Sync

The **Custom Catalogs** page supports **auto-catalog sync** — automatically classifying your entire media library into streaming-service-style catalogs (e.g., Netflix, Prime Video, Disney+) using TMDb's watch-provider data. Settings include which providers to enable and how frequently to sync.


---


# 💳 Subscription Management

The Subscription Management system allows you to **monetise access** to your Telegram Stremio server. When enabled, users must have an active subscription to stream content.

## 📋 Subscription Plans

Admins can create and manage subscription plans from the **Admin Panel → Subscription Management** page.

Each plan has:
- **Name** (e.g. `Monthly`, `Quarterly`)
- **Duration** in days
- **Price** (for display)
- **Description**

Plans are stored in MongoDB and can be added, edited, or deleted at any time without restarting.

---

## 🤖 Bot Payment Flow

Users interact with the bot to subscribe:

```
User → /start → selects plan → sends payment screenshot
      → Approver gets notification → Approve / Reject
      → On Approve:
          ✅ Subscription saved to DB
          🔑 Stremio addon token auto-generated
          📨 User receives Stremio install link + group invite
```

**Approver actions** (available to `APPROVER_IDS`):

| Button | Action |
| :--- | :--- |
| ✅ Approve | Activates subscription, generates addon token, invites user to group |
| ❌ Reject | Notifies user with rejection message |

---

## 🗃️ Access Management

The **Admin Panel → Access Management** page gives admins full control over all users and their addon tokens.

### Columns Shown

| Column | Description |
| :--- | :--- |
| Status | 🟢 Active / 🔴 Expired |
| User | Display name or `User {id}` |
| Addon Link | Stremio install URL + copy button |
| Created | Token creation date |
| Expires | Subscription expiry date |
| Actions | Buttons for managing the user |

### Action Buttons

| Button | Description |
| :--- | :--- |
| 📅 **Assign** | Assign or extend a subscription plan (adds days) |
| ➕ **Extend** | Add extra days to an active subscription |
| ➖ **Reduce** | Subtract days from an active subscription |
| 🚫 **Revoke** | Wipe subscription entirely (marks expired) |
| 🗑️ **Del Token** | Delete the addon token only (user still subscribed) |
| 🔗 **Link User ID** | Link an old/orphan token to a Telegram user ID to enable management |

> 💡 Manually created (old) tokens that have no linked user ID show a **🔗 Link User ID** button. Once linked, all action buttons become available.

### Search & Filtering

- 🔍 Search by user name or ID
- Filter by status: All / Active / Expired
- Pagination with configurable page size

---

## 🎬 Stremio Addon Integration

### Per-User Addon Token

Each user gets a **unique addon token** automatically generated on payment approval. Their Stremio addon URL is:

```
https://your-domain.com/stremio/{token}/manifest.json
```

### Dynamic Manifest

The addon manifest updates dynamically per user:

| Scenario | Addon Name | Description |
| :--- | :--- | :--- |
| Active, has expiry | `Telegram — Expires 28 Mar 2026` | 📅 Subscription active until 28 Mar 2026 |
| Active, no expiry | `Telegram — Active` | ✅ Subscription active |
| Default (no subscription mode) | `Telegram` | Standard description |

The manifest `version` encodes the expiry date — when an admin extends or revokes a subscription, the version changes and Stremio detects an update.

### Subscription Stream Gating

When the subscription feature is enabled, the addon checks every stream request and shows a single actionable entry instead of the streams when the user isn't eligible. In both cases the stream link opens **your bot** (derived automatically from the bot's username — there is no URL to configure).

**Plan expired** — the user's subscription has lapsed:

```json
{
  "name": "🚫 Plan Expired",
  "title": "Your plan is expired.\nRenew it from the bot to continue watching.",
  "url": "https://t.me/your_bot"
}
```

**Not joined** — the user is active but has left / never joined the subscription channel (the `Subscription Group ID`):

```json
{
  "name": "📢 Join Required",
  "title": "First join the channel to stream it.\nTap here to open the bot and join.",
  "url": "https://t.me/your_bot"
}
```

Clicking the stream name opens the bot directly so the user can renew or rejoin. The membership check fails open — if Telegram is briefly unreachable or the bot can't read the group, legitimate users are never blocked.

### Configure & Reinstall Page

Every addon has a **Configure page** at:

```
https://your-domain.com/stremio/{token}/configure
```

This page shows:
- User name, subscription status, expiry date
- **⚡ Install / Update in Stremio** button (Stremio Web install flow)
- Manual install steps + **📋 Copy URL** button

The ⚙️ gear icon in Stremio opens this page so users can reinstall after an admin updates their subscription.

---


# 🤖 Bot Commands

Below is the list of available bot commands and their usage within the Telegram bot.

### Command List

| Command | Description |
| :--- | :--- |
| **`/start`** | Returns your **Addon URL** for direct installation in **Stremio**. When subscriptions are enabled, shows the plan selection menu to unauthenticated users. |
| **`/stats`** | Displays a live dashboard — movie/TV/episode counts, total streams, DB size, uptime, and channel count. *(Owner only)* |
| **`/log`** | Sends the latest **log file** for debugging or monitoring. *(Owner only)* |
| **`/set`** | Used for **manual uploads** by linking IMDb/TMDb URLs. *(Owner only)* |
| **`/restart`** | Pulls the latest update from the upstream repository and restarts the bot. *(Owner only)* |

### `/set` Command Usage

The `/set` command is used to manually associate a specific Movie or TV show with its IMDb/TMDb metadata before uploading files to your channel.

**Command:**

```
/set <imdb-or-tmdb-url>
```

**Example:**

```
/set https://www.imdb.com/title/tt0468569/
```

**Steps:**

1. Send the `/set` command followed by the **IMDb or TMDb URL** of the movie or show.
2. **Forward the related movie or TV show files** to your AUTH channel.
3. Once all files are uploaded, **clear the default link** by sending `/set` without any URL.

💡 **Tip:** Use `/log` if you encounter any upload or parsing issues.


---


# 🔧 Configuration Guide

> 😌 **Don't worry — setup is easier than it looks.**
> You only fill in **a handful of values once** inside a single file called `config.env`. Everything else (TMDB key, channels, admin login, subscriptions, proxy…) is configured later from a friendly **Web Settings page** — no code, no restarts.

Think of configuration as **two simple layers**:

| Layer | Where | When you set it | What goes here |
| :--- | :--- | :--- | :--- |
| 🧱 **Startup** | `config.env` file | Once, before first launch | Core credentials needed to boot |
| 🎛️ **Runtime** | **Web Settings page** | Anytime, after launch | Everything else — saved to the database, applied live |

---

## 🪜 Step 1: Create Your config.env File

After cloning the project, copy the sample file and open it for editing:

```bash
cp sample_config.env config.env
nano config.env
```

Fill in these values:

| Variable | Required | What it is |
| :--- | :---: | :--- |
| `API_ID` | ✅ | Telegram API ID (from my.telegram.org) |
| `API_HASH` | ✅ | Telegram API Hash (from my.telegram.org) |
| `BOT_TOKEN` | ✅ | Your bot token (from @BotFather) |
| `OWNER_ID` | ✅ | Your numeric Telegram user ID |
| `DATABASE` | ✅ | **Two** MongoDB URIs, separated by a comma |
| `PORT` | ✅ | Web server port (keep `8000` unless it's busy) |
| `USER_SESSION_STRING` | ⬜ | Optional but recommended — enables **Global Search**, Userbot fallback operations, and Userbot-first Replace Mode deletion |
| `ADMIN_USERNAME` | ⬜ | Recommended admin login name; when paired with `ADMIN_PASSWORD`, it can recover an old saved login |
| `ADMIN_PASSWORD` | ⬜ | Recommended admin password; set it as a secret, never commit it |

A completed file looks like this (these are just example values):

```env
API_ID="1234567"
API_HASH="abc123def456ghi789jkl012mno345pq"
BOT_TOKEN="1234567890:AAEabcdEFGhijkLMnOPqrsTUVwxyz12345"
USER_SESSION_STRING=""
OWNER_ID="987654321"
DATABASE="mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/tracking,mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/storage1"
PORT="8000"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="choose-a-strong-password"
```

> 💾 To save in nano: press `Ctrl + O`, then `Enter`, then `Ctrl + X`.

> ℹ️ All other settings (AUTH_CHANNEL, TMDB_API, BASE_URL, subscription options, proxy, etc.) are configured from the **Web Settings page** after first launch — no need to add them to `config.env`.

---

## 🔑 Step 2: How to Get Each Value

Take it one line at a time — each value comes from a quick, free step.

### 🆔 API_ID & API_HASH
1. Go to **https://my.telegram.org** and log in with your phone number.
2. Open **API development tools**.
3. Create an app (any title works, e.g. `stremio`).
4. Copy **App api_id** → `API_ID` and **App api_hash** → `API_HASH`.

### 🤖 BOT_TOKEN
1. Open **@BotFather** in Telegram.
2. Send `/newbot` and follow the prompts (choose a name and a username).
3. Copy the token it gives you → `BOT_TOKEN`.
4. ⭐ Add this bot as an **admin** in every channel you'll use for media.

### 👤 OWNER_ID
1. Open **@userinfobot** in Telegram (or send `/id` to **@MissRose_bot**).
2. It replies with your numeric ID → `OWNER_ID`.

### 🗄️ DATABASE (two MongoDB URIs)
You need **two** free MongoDB databases — the first stores tracking/metadata, the second stores your media references.

1. Create a free account at **https://www.mongodb.com/atlas** (the forever-free **M0** tier is enough to start).
2. Create a cluster → in **Database Access**, add a database user and password.
3. In **Network Access**, add `0.0.0.0/0` (allow access from anywhere).
4. Click **Connect → Drivers** and copy the connection string, e.g.
   `mongodb+srv://user:pass@cluster0.xxxx.mongodb.net/`
5. Add a database name at the end of each (e.g. `/tracking` and `/storage1`).
6. Put **both** strings on one line, separated by a comma:
   ```
   DATABASE="mongodb+srv://.../tracking,mongodb+srv://.../storage1"
   ```

> 💡 You can use the **same cluster** for both — just give them two different database names. Need more space later? Add extra storage databases from the Web Settings page (no restart required).

### 🔢 PORT
Leave it as `8000` unless that port is already in use. Your reverse proxy / domain will point here.

### 📱 USER_SESSION_STRING (optional)
Recommended when you want **Global Search** or want Replace Mode to delete older channel posts through your Telegram user account before trying the bot. See **Step 3** below. Leave it empty only when neither feature is needed.

---

## 📱 Step 3: Generate Your Telegram Session String

> 😊 **No app installation required — and it's safe.**
> A session string is simply a "stay logged in" token for **your own** Telegram account, exactly like signing into Telegram Web. The bot never sees your password, and you can revoke access anytime from **Telegram → Settings → Devices**.

> ⏭️ **Skip this step** only if you do not need Global Search and do not want Userbot-first deletion for Replace Mode.

### 🌐 Recommended Method: Google Colab (works in a phone browser)

Open the **[Telegram User Session String Generator](https://colab.research.google.com/github/rjriajul/session/blob/main/user_tgsess.ipynb)**, then follow the notebook prompts.

1️⃣ Sign in to Google if Colab asks.

2️⃣ Enter your Telegram **API ID** and **API HASH** from [my.telegram.org](https://my.telegram.org).

3️⃣ Confirm the Telegram login code and your 2-step password when prompted.

4️⃣ Copy the generated value and save it as `USER_SESSION_STRING`:

- **VPS / local deployment:** add it to `config.env`.
- **Hugging Face Spaces:** add it in **Settings → Variables and secrets** as a Secret named `USER_SESSION_STRING`.

> 🔒 **Keep the session string private.** It grants access to your Telegram account. Never share it, send it to another person, or commit it to GitHub. To revoke it, remove the related session from **Telegram → Settings → Devices**, then generate a new one.

---

## 🧩 Step 4: Configure Everything Else (Web Settings Page)

Once the server is running, open it in your browser:

| Setup | Open this URL |
| :--- | :--- |
| **VPS with a domain** | `https://your-domain.com` |
| **Local / direct IP** | `http://<your-vps-ip>:8000` |

You'll land on the **login page** (`/login`). Sign in with the default credentials:

```
Username: admin
Password: admin
```

Then go to **Settings** (`/admin/settings`).

> 🚨 **Do this first:** change the admin password in the **Admin Authentication** card, then click **Save Settings**.

Everything below is stored in the database and applied **instantly — no restart needed**.

### ⚙️ General
| Option | What it does |
| :--- | :--- |
| **Replace Mode** | When a new file has the same quality (`720p`, `1080p`…) as an existing one, it replaces the old entry. Recommended **ON**. |
| **Hide Catalog** | Hides the public Stremio catalog (direct streams still work). |

### 🛡️ Admin Authentication
| Field | What to enter |
| :--- | :--- |
| **Admin Username / Password** | Your Web Panel login. Leave the password blank to keep the current one. **Change the defaults right away.** |
| **AUTH_CHANNELS** | The channel(s) the bot indexes and streams from. Add each one by `@username` or `-100…` ID. Make sure your bot is an **admin** in each channel. |

### 🎬 Media & Content
| Field | What to enter |
| :--- | :--- |
| **TMDB API Key** | A free TMDB **v3** key from themoviedb.org → Settings → API. Powers automatic metadata matching and auto-catalog sync. |
| **Base URL** | Your public address, e.g. `https://your-domain.com`. Hugging Face builds can auto-detect `SPACE_HOST` when this is blank, but saving the correct public URL is still recommended. |
| **Upstream Repo / Branch** | Optional — used by `/restart` to auto-update (e.g. repo `weebzone/Telegram-Stremio`, branch `master`). |

### 💳 Subscription (optional)
Turn this on to monetise access. Set the **Subscription Group ID**, **Payment Instructions** (your UPI / bank / PayPal text), an optional **Payment QR image URL**, and the **Approver IDs** (who can approve requests). Renewal and "join the channel" prompts shown in Stremio point users back to **your bot automatically** — no separate URL to configure. The full flow is described in [Subscription Management](#-subscription-management).

### 🌐 Global Search (optional)
Requires `USER_SESSION_STRING` in `config.env` plus one app restart to unlock. Then enable the toggle and add the **channel IDs** to search. Results that aren't in your local catalog are tagged **🌐 GLOBAL** in Stremio.

### 🌐 Proxy (optional)
Set an **HTTP Proxy URL** for outbound metadata/API requests, and optionally **show both** proxied and direct stream links.

### 🗄️ Extra Storage Databases
Your first two databases (from `config.env`) are **locked** as *Tracking* and *Storage 1*. Add more MongoDB URIs here to expand storage capacity — 🟢 means connected. Remove entries only from the **end** of the list, since existing media reference databases by position.

### 📨 Multi-Token Clients
Add extra **bot tokens** for faster parallel streaming under heavy load. Create more bots with @BotFather, add them as **admins** in all your AUTH channels, then paste their tokens here. Changes apply immediately.

> ✅ Click **Save Settings** when you're done. That's it — you're live!

---


# 🚀 Deployment Guide

This guide will help you deploy your **Telegram Stremio Media Server** using either Heroku or a VPS with Docker.

## ✅ Recommended Prerequisites

**Supported Servers:**

- 🟣 **Heroku**
- 🟡 **Hugging Face Spaces**
- 🟢 **VPS**

Before you begin, choose your deployment target. Requirements vary:

| Method | Needs VPS | Needs Domain | Cost |
| :--- | :---: | :---: | :--- |
| 🟣 **Heroku** | ❌ | ❌ | Free / paid |
| 🟡 **Hugging Face Spaces** | ❌ | ❌ | Free CPU tier available |
| 🟢 **VPS (Recommended)** | ✅ | ✅ | VPS + domain required |


## 🐙 Heroku Guide

Follow the instructions provided in the Google Colab Tool to deploy on Heroku.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/weebzone/Colab-Tools/blob/main/telegram%20stremio.ipynb)


## 🤗 Hugging Face Spaces Guide

This repository is already configured as a Docker Space and uses **port `8000`** consistently:

- `README.md` YAML: `app_port: 8000`
- `sample_config.env`: `PORT="8000"`
- Backend default: `PORT=8000`

> Do not change only one of these values. A mismatch between the Hugging Face `app_port` and the Uvicorn port causes the Space health check to fail and can leave the Space in a **Restarting** loop.

### 1️⃣ Create the Space

1. Open Hugging Face and create a new **Docker** Space.
2. Use **Private** visibility when possible because logs and repository files may contain operational details.
3. Upload or push the complete repository, including the YAML block at the top of this README.

### 2️⃣ Add Variables and Secrets

Open **Space → Settings → Variables and secrets** and add:

| Name | Type | Required | Value |
| :--- | :--- | :---: | :--- |
| `API_ID` | Secret | ✅ | Telegram API ID |
| `API_HASH` | Secret | ✅ | Telegram API Hash |
| `BOT_TOKEN` | Secret | ✅ | Main bot token |
| `OWNER_ID` | Variable/Secret | ✅ | Numeric Telegram user ID |
| `DATABASE` | Secret | ✅ | Tracking and storage MongoDB URIs separated by a comma |
| `PORT` | Variable | ✅ | `8000` |
| `USER_SESSION_STRING` | Secret | ⬜ | Global Search and Userbot-first deletion |
| `TMDB_API` | Secret | ⬜ | TMDb v3 API key; can repair a blank DB setting on startup |
| `BASE_URL` | Variable | ⬜ | Full Space URL; otherwise `SPACE_HOST` is auto-detected |
| `ADMIN_USERNAME` | Secret | ⬜ | Admin panel username |
| `ADMIN_PASSWORD` | Secret | ⬜ | Admin panel password |

### 3️⃣ Deploy

Push the repository to the Space. A healthy startup log should include:

```text
Telegram-Stremio Started Successfully!
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

Database success is shown separately:

```text
Tracking Database connected successfully
Storage 1 Database connected successfully
```

### 4️⃣ Configure Runtime Settings

After the Space is running:

1. Open the Space URL and sign in to the web panel.
2. Open **Settings**.
3. Save the **TMDb API key**, **Base URL**, AUTH channels, and other runtime settings.
4. Empty MongoDB runtime values can be repaired from non-empty `TMDB_API`, `BASE_URL`, or Hugging Face `SPACE_HOST` environment values on startup. Non-empty WebUI values remain authoritative.

### 5️⃣ Install the Addon

The root route below is **not** the addon manifest and may return `404`:

```text
https://your-space.hf.space/manifest.json
```

Use the personal tokenized manifest URL returned by the bot or web panel:

```text
https://your-space.hf.space/stremio/YOUR_TOKEN/manifest.json
```

### 🔁 Updating the Space

Push a new commit to trigger a rebuild:

```bash
git add .
git commit -m "Update Telegram-Stremio"
git push
```

The startup script runs the repository updater before starting the backend. Keep the repository structure intact when uploading ZIP contents.

### 📋 Hugging Face Troubleshooting

| Log or symptom | Meaning / action |
| :--- | :--- |
| Space remains **Restarting** | Confirm both `app_port` and `PORT` are `8000` |
| `tmdb_api=empty` or TMDb `401 Unauthorized` | Add a valid TMDb v3 API key |
| `base_url=empty` | Add `BASE_URL`; on HF, `SPACE_HOST` can also supply it automatically |
| `GET /manifest.json 404` | Use `/stremio/YOUR_TOKEN/manifest.json` instead |
| DB connection timeout | Check Atlas password, network access, DNS, and MongoDB availability |
| `MESSAGE_DELETE_FORBIDDEN` from bot | Configure a valid `USER_SESSION_STRING`; the build tries Userbot first |


## 🐳 VPS Guide

This section explains how to deploy your **Telegram Stremio Media Server** on a VPS using **Docker Compose (recommended)** or **Docker**.


### 1️⃣ Step 1: Clone & Configure the Project

```bash
git clone https://github.com/weebzone/Telegram-Stremio
cd Telegram-Stremio
mv sample_config.env config.env
nano config.env
```

- Fill in all required variables in `config.env`.
- Press `Ctrl + O`, then `Enter`, then `Ctrl + X` to save and exit.

### ⚙️ Step 2: Choose Your Deployment Method

You can deploy the server using either **Docker Compose (recommended)** or **plain Docker**.



### 🟢 **Option 1: Deploy with Docker Compose (Recommended)**

Docker Compose provides an easier and more maintainable setup, environment mounting, and restart policies.

#### 🚀 Start the Container

```bash
docker compose up -d
```

Your server will now be running at:
➡️ `http://<your-vps-ip>:8000`

---

#### 🛠️ Update `config.env` While Running

If you need to modify environment values (like `DATABASE`, `BOT_TOKEN`, etc.):

1. **Edit the file:**

   ```bash
   nano config.env
   ```
2. **Save your changes:** (`Ctrl + O`, `Enter`, `Ctrl + X`)
3. **Restart the container to apply updates:**

   ```bash
   docker compose restart
   ```

⚡ Since the config file is mounted, you **don't need to rebuild** the image — changes apply automatically on restart. All other settings can be changed live from the Web Settings page without restarting.



### 🔵 **Option 2: Deploy with Docker (Manual Method)**

If you prefer not to use Docker Compose, you can manually build and run the container.

#### 🧩 Build the Image

```bash
docker build -t telegram-stremio .
```

#### 🚀 Run the Container

```bash
docker run -d -p 8000:8000 telegram-stremio
```

Your server should now be running at:
➡️ `http://<your-vps-ip>:8000`



### 🌐 Step 3: Add Domain (Required)

#### 🅰️ Set Up DNS Records

Go to your domain registrar and add an **A record** pointing to your VPS IP:

| Type | Name | Value             |
| ---- | ---- | ----------------- |
| A    | @    | `195.xxx.xxx.xxx` |


#### 🧱 Install Caddy (for HTTPS + Reverse Proxy)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

#### ⚙️ Configure Caddy

1. **Edit the Caddyfile:**

   ```bash
   sudo nano /etc/caddy/Caddyfile
   ```

2. **Replace contents with:**

   ```caddy
   your-domain.com {
       reverse_proxy localhost:8000
   }
   ```

   - Replace `your-domain.com` with your actual domain name.
   - Adjust the port if you changed it in `config.env`.

3. **Save and reload Caddy:**

   ```bash
   sudo systemctl reload caddy
   ```


✅ Your API will now be available securely at:
➡️ `https://your-domain.com`


# 📺 Setting Up Your App (Nuvio Recommended)

Your media server works as a standard **Stremio-style addon**, so it plays in any compatible client. For the **best compatibility and smoothest experience across devices, we recommend the [Nuvio](https://play.google.com/store/apps/details?id=com.nuvio.app) app** — a free, open-source media hub for **Android, Android TV, Fire TV, iOS, Windows, and TV** that supports Stremio addon manifest URLs natively.

> 💡 Already using **Stremio**? It works too — just install the same addon URL below. Nuvio simply tends to handle these Telegram streams more reliably across more devices.

## 📥 Step 1: Install Nuvio

Download Nuvio from an official source:

| Platform | Source |
| :--- | :--- |
| **Android / Android TV / Fire TV** | [Google Play](https://play.google.com/store/apps/details?id=com.nuvio.app) |
| **All platforms / latest builds** | [GitHub — tapframe/NuvioStreaming](https://github.com/tapframe/NuvioStreaming) |

> 🔗 *(Optional)* Connect **Trakt** in the app to sync your watch history and progress across devices.

## 🌐 Step 2: Add the Addon

1. Open **Nuvio** and go to the **Addons** section.
2. Paste your addon **manifest URL** and install it:

| Deployment Method | Addon URL |
| :--- | :--- |
| **Heroku** | `https://<your-heroku-app>.herokuapp.com/stremio/YOUR_TOKEN/manifest.json` |
| **Hugging Face Spaces** | `https://<your-hf-username>-telegram-stremio.hf.space/stremio/YOUR_TOKEN/manifest.json` |
| **Custom Domain (VPS)** | `https://<your-domain>/stremio/YOUR_TOKEN/manifest.json` |

3. Done! 🎉 Your Telegram library now appears in the catalog and streams directly.

> 🔑 If you run in **subscription mode**, each user installs their own **personal** addon URL (`/stremio/{token}/manifest.json`) that the bot gives them automatically via `/start`.


## 🏷️ Nuvio Stream Badges

This project no longer bundles badge JSON or PNG files. Import one of these external Nuvio badge profiles instead.

1. Open **Nuvio → Settings → Streams → Import badge profile**.
2. Paste the URL for the style you want:

| Style | Badge profile URL |
| :--- | :--- |
| **Transparent badges** | `https://gist.github.com/tharindu899/53ad15643824c59150d7a699f27557b1/raw/e599169242a73359fedfd59e453bf7dd66a54389/transparent-badges-nuvio` |
| **Mono badges** | `https://gist.githubusercontent.com/tharindu899/81fe72ad8a2adede6647ee2e0088e1ac/raw/d5959030e02fd8e04ef57d9f928e6193ef2b8a23/mono-badges-nuvio` |
| **Solid badges** | `https://gist.githubusercontent.com/tharindu899/b3cc3335091e25619e377dfa7fb4a1c7/raw/59a0675eaa7ab5922189fb550dfa189f497dc337/solid-badges-nuvio` |

Import the profile that matches your preferred look. All three profiles stay external, so deployments do not need local badge files or a `/nuvio-badges.json` route.


## 🏅 Contributors

|<img width="80" src="https://avatars.githubusercontent.com/u/113664541">|<img width="80" src="https://avatars.githubusercontent.com/u/113652899">|<img width="80" src="https://avatars.githubusercontent.com/u/13152917">|<img width="80" src="https://avatars.githubusercontent.com/u/14957082">|<img width="80" src="https://raw.githubusercontent.com/vflixa1prime/Readme/main/VFlixPRime.png">|
|:---:|:---:|:---:|:---:|:---:|
|[`Karan`](https://github.com/Weebzone)|[`Tharindu`](https://github.com/tharindu899)|[`Stremio`](https://github.com/Stremio)|[`ChatGPT`](https://github.com/OPENAI)|[`VFlix Prime`](https://t.me/vflixprime2)|
|Author · [weebzone](https://github.com/weebzone)|Fork & Improvements · [TharinduHub](https://t.me/TharinduHub)|Stremio SDK|Refactor|Community Support
