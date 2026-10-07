# Vorha

Vorha is a personal sound library built around public TikTok and YouTube videos. Paste a video link, and Vorha reads its metadata, fetches the soundtrack, and plays it audio-only in a persistent player — no video is shown.

The backend resolves the video's audio track with `yt-dlp`, transcodes it to MP3 with `ffmpeg`, caches the file on the server, and streams it to the browser with byte-range support so seeking works. Metadata comes from each platform's public oEmbed endpoint plus the extractor.

**This downloads media from TikTok and YouTube.** That is a deliberate change from a metadata-only design and it conflicts with both platforms' Terms of Service; the audio itself is usually third-party copyrighted music. Keep the deployment private, do not redistribute cached files, and take responsibility for how you use it. Set `AUDIO_EXTRACTION_ENABLED=false` to fall back to the metadata-only behaviour, where users attach an audio or video file they are authorized to use (stored in browser-local IndexedDB, played soundtrack-only).

## Features

- Responsive dark music-library interface with Discover, My Library, and Playlists views
- Audio-only playback straight from a pasted TikTok or YouTube URL, with the picture hidden
- Public video metadata lookup, URL validation, and request throttling for both platforms
- TikTok short-link resolution, YouTube link normalization, and bounded retries for temporary metadata service failures
- Server-side audio extraction (`yt-dlp` + `ffmpeg`), on-disk cache, and range-request streaming
- Fallback import of user-authorized audio or video files, stored locally in the current browser
- Email registration and login with Argon2 password hashes, Telegram OIDC login, and an HttpOnly JWT cookie
- MySQL-backed sounds, playlists, favorites, and listening history
- Playlist creation, rename, deletion, ordering, and sound management
- Search across a signed-in user's saved library
- Persistent bottom audio player controls with queue, shuffle, and repeat
- Optional Redis metadata cache with graceful fallback
- Docker Compose development stack with MySQL and audio-cache persistence

## Architecture

```text
frontend/  Next.js App Router, React, TypeScript, Tailwind CSS
backend/   FastAPI, Pydantic, SQLAlchemy 2, Alembic, yt-dlp + ffmpeg
database/  MySQL 8.4
cache/     Redis 7 (optional; application remains usable without it)
```

The frontend uses a central API client in `frontend/lib/api`. FastAPI routers call SQLAlchemy models, the per-platform metadata services, and the audio extraction service. `POST /sounds/analyze` routes a pasted link to the service that owns its host and stores the result under `source_platform` (`tiktok` or `youtube`). Authentication state is held in a SameSite, HttpOnly cookie, with JWT claims expiring after the configured duration. Extracted MP3s live outside the database in `AUDIO_CACHE_DIR` and are served by `GET /sounds/{id}/stream`.

## Requirements

- Docker Engine and Docker Compose v2 (recommended)
- For running services outside Docker: Node.js 20+ and Python 3.12+

## Environment

The Compose stack starts with safe-for-local-development defaults. For a customized local environment, copy the example and change its values:

```bash
cp .env.example .env
```

Set unique `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, and `JWT_SECRET_KEY` values before exposing any service beyond your own machine. Do not commit `.env`.

Backend settings: `APP_NAME`, `ENVIRONMENT`, `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REDIS_URL`, `FRONTEND_URL`, `TELEGRAM_CLIENT_ID`, `TELEGRAM_BOT_ID`, `AUDIO_EXTRACTION_ENABLED`, `AUDIO_CACHE_DIR`, `AUDIO_BITRATE`, `AUDIO_MAX_BYTES`, and `AUDIO_EXTRACT_TIMEOUT_SECONDS`.

To enable Telegram login, create a bot with [@BotFather](https://t.me/BotFather), open its **Login Widget** settings, and add your frontend origin (for local development, `http://localhost:3000`) to the allowed URLs. Set both `TELEGRAM_CLIENT_ID` (from BotFather) and `TELEGRAM_BOT_ID` (the numeric bot ID, before the colon in its bot token) in `.env`; keep the token itself private. `TELEGRAM_BOT_ID` is required because Telegram rejects the login request without it. The frontend opens Telegram's official login popup; the backend verifies the signed ID token and nonce before creating the session. Telegram accounts are created without an email address; account linking is not included yet.

`AUDIO_EXTRACTION_ENABLED=false` disables downloading and returns metadata only. `AUDIO_CACHE_DIR` defaults to `./.audio-cache` and is a Docker volume in Compose.

Frontend setting: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000/api/v1`).

## Run with Docker

From the repository root:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). FastAPI docs are at [http://localhost:8000/docs](http://localhost:8000/docs), and health checks are at `/health` and `/health/ready`. The backend applies Alembic migrations before starting. MySQL data persists in the `mysql_data` volume and extracted audio in the `audio_cache` volume.

Stop services with `Ctrl+C`, or run `docker compose down`. To remove the local database volume too, run `docker compose down -v`.

## Run services locally

`ffmpeg` (with `ffprobe`) must be on `PATH` for audio extraction; the backend Docker image installs it. On Fedora/Debian: `sudo dnf install ffmpeg` or `sudo apt install ffmpeg`.

Start MySQL and Redis first (or point the settings to existing instances):

```bash
docker compose up -d mysql redis
```

Backend:

```bash
cp backend/.env.example backend/.env
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

For a local (non-Docker) backend, set `DATABASE_URL` with host `localhost` and the same MySQL password configured for Compose.

Frontend (in another terminal):

```bash
cp frontend/.env.example frontend/.env.local
cd frontend
npm install
npm run dev
```

## Database migrations

Run from `backend/` after configuring `DATABASE_URL`:

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Do not modify a live database schema by hand. Review autogenerated migrations before applying them.

## API overview

Base path: `/api/v1`. Interactive OpenAPI documentation is served at `/docs`.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/telegram/nonce`, `POST /auth/telegram/login`, `GET /auth/me`, `POST /auth/logout` |
| Sounds | `POST /sounds/analyze`, `POST /sounds/{id}/audio`, `GET /sounds/{id}/stream`, `GET /sounds/{id}`, `GET /sounds?q=...&page=1&limit=20` |
| Playlists | `GET/POST /playlists`, `GET/PATCH/DELETE /playlists/{id}`, add/remove/reorder sounds under `/playlists/{id}/sounds` |
| Favorites | `GET /favorites`, `POST/DELETE /favorites/{sound_id}` |
| History | `GET/POST/DELETE /history`, `PATCH /history/{sound_id}` |

Errors use a stable envelope: `{ "success": false, "error": { "code": "...", "message": "..." } }`.

`POST /sounds/analyze` reads metadata and then tries to extract the audio; a failed extraction still returns the metadata with `is_playable: false`. `POST /sounds/{id}/audio` retries that extraction and reports the reason it failed. `GET /sounds/{id}/stream` serves the cached MP3, requires the session cookie, supports `Range`, and extracts on demand if the cache was cleared.

Audio-specific error codes: `VIDEO_NOT_FOUND`, `VIDEO_RESTRICTED`, `UNSUPPORTED_URL`, `RATE_LIMITED`, `AUDIO_EXTRACTION_DISABLED`, `AUDIO_EXTRACTION_UNAVAILABLE`, `AUDIO_EXTRACTION_TIMEOUT`, `AUDIO_EXTRACTION_FAILED`, `AUDIO_TOO_LARGE`.

## Tests and checks

```bash
cd backend && pytest
cd frontend && npm run typecheck && npm run build
```

The backend tests use an isolated SQLite database, stub the external oEmbed responses, and stub audio extraction so no media is downloaded. Extraction is disabled and the cache directory is redirected to a temporary path for every test. The production schema and Compose stack use MySQL.

## Security and integration limits

- Passwords use Argon2; plaintext passwords are never stored.
- JWTs are held in an HttpOnly, SameSite=Lax cookie; production cookies require HTTPS.
- SQLAlchemy binds values through prepared statements; URL lookup accepts only HTTPS TikTok and YouTube hosts.
- Cached audio filenames are namespaced per platform (`youtube-<id>.mp3`; TikTok keeps its original bare ids), so ids from different sites cannot collide.
- Sound analysis, audio preparation, and streaming are rate-limited per source IP. Keep CORS restricted to the frontend origin.
- The stream endpoint requires authentication, and cache filenames come from a validated video id (`[A-Za-z0-9_-]{4,80}`) so requests cannot traverse outside `AUDIO_CACHE_DIR`.
- Extraction runs at most `MAX_CONCURRENT_EXTRACTIONS` at a time, with a per-request timeout and a size cap, so one long video cannot exhaust the worker.
- **The server downloads and stores audio from TikTok and YouTube.** This breaches both platforms' Terms of Service, and the audio is normally third-party copyrighted music. Keep the instance private, do not publish or redistribute cached files, and prune `AUDIO_CACHE_DIR`. Set `AUDIO_EXTRACTION_ENABLED=false` to stop downloading.
- Both platforms actively block automated access. Extraction will fail for private, removed, age-restricted, region-locked, or bot-gated videos (YouTube often gates datacenter IPs behind a sign-in check), and it can break without warning when either site changes. The local-file import path stays available as a fallback.
- `yt-dlp` needs periodic upgrades to keep working: `pip install -U yt-dlp` (or rebuild the backend image).

## Project layout

```text
frontend/
  app/                 Next.js pages and global styling
  lib/api/              Centralized typed API client
  types/                Shared frontend response types
backend/
  app/core/             Settings, database, security, dependencies
  app/models/           SQLAlchemy models
  app/routers/          REST endpoints
  app/schemas/          Pydantic request and response types
  app/services/         TikTok and YouTube metadata integration, audio extraction
  alembic/              Database migration environment and revisions
  tests/                API and service tests
docker-compose.yml      MySQL, Redis, backend, and frontend services
```
