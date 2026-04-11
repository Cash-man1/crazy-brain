# Crazy Brain — Deploy su Render da zero (guida tecnica)

Questa guida descrive un rilascio **ripetibile** con frontend statico, API Docker, Redis opzionale e worker live leggero. Non sostituisce la consulenza legale sul gioco d’azzardo o i ToS dei siti terzi: l’integrazione con `api-cs.casino.org` è una **dipendenza esterna** che può cambiare senza preavviso.

---

## Ruoli dei servizi Render (nomi nel `render.yaml` — non confonderli)

Questi sono i **quattro pilastri** del deploy consigliato. I nomi corrispondono al Blueprint in repo; puoi rinominarli nel pannello Render, ma è utile tenerli allineati per log, metriche e variabili incrociate.

| Nome servizio Render | Tipo | Ruolo |
|----------------------|------|--------|
| **`crazy-brain-web`** | **Static Site** | Frontend Vite/React: solo asset statici e chiamate al backend via `VITE_API_URL`. Nessuna logica server. |
| **`crazy-brain-api`** | **Web Service** (Docker) | API FastAPI leggera: auth, Stripe, Telegram, brain, JSON dashboard. Preferire **`Dockerfile.api`** + `SCRAPER_PLAYWRIGHT_FALLBACK=0` per RAM bassa (vedi sotto). |
| **`crazy-brain-live-worker`** | **Background Worker** (Docker) | Processo separato: solo polling Evolution (`httpx`) e scrittura su **Redis** (`run_live_worker.py`). Nessun browser, bassa RAM. |
| **`REDIS_URL`** | **Add-on Redis** (Render Redis o Upstash) | **Consigliato in produzione:** una sola URL usata da (1) **cache JSON** della dashboard pubblica (`external_public_cache`) e (2) **buffer righe live** (`live_rows_redis`). Sull’API imposta anche `LIVE_ROWS_FROM_REDIS=1` se vuoi che il web legga prima Redis popolato dal worker. |

**In sintesi:** il browser parla solo con **`crazy-brain-web`** → API; i dati live pesanti non devono stare nel processo **`crazy-brain-api`** se usi worker + Redis; senza Redis l’API può ancora usare Evolution in-process, con più RAM sullo stesso dyno.

---

## A. Architettura consigliata (dettaglio)

| Componente | Render | Immagine / comando | Ruolo |
|------------|--------|-------------------|--------|
| **Frontend** | Static Site | `frontend/` → `npm ci && npm run build` | Solo UI, chiama API via `VITE_API_URL` |
| **API** | Web Service (Docker) | `backend/Dockerfile` **oppure** `backend/Dockerfile.api` | Auth, Stripe, Telegram, brain, serving dashboard JSON |
| **Worker live** (opzionale) | Background Worker | `backend/Dockerfile.worker` | Solo `httpx` + scrittura Redis (bassa RAM) |
| **Redis** | Render Redis o Upstash | — | Cache payload pubblico + buffer righe live |

**Percorso dati live (consigliato in produzione)**

1. Worker chiama l’API JSON Evolution (`crazytime_api.py`) ogni pochi secondi.
2. Scrive JSON in Redis (`LIVE_ROWS_REDIS_KEY`, TTL configurabile).
3. L’API legge prima Redis se `LIVE_ROWS_FROM_REDIS=1`, poi Evolution diretta, poi (solo se abilitato) Playwright.

**RAM**

- `Dockerfile` (Playwright + Chromium): massima compatibilità, **RAM alta**.
- `Dockerfile.api` + `SCRAPER_PLAYWRIGHT_FALLBACK=0` + Evolution o Redis: **RAM molto più bassa**.

---

## B. Preparazione repository

- `backend/` — FastAPI, `main.py`, moduli brain, `crazytime_api.py`, `live_data_pipeline.py`, `live_rows_redis.py`.
- `frontend/` — Vite/React.
- `render.yaml` — Blueprint di esempio (aggiusta nomi e regione).
- `docs/RENDER_DEPLOY.md` — questa guida.
- `backend/.env.example` — elenco variabili.

---

## C. Creazione servizi su Render

1. **Redis** (o Upstash): crea istanza, copia `REDIS_URL`.
2. **Backend**: New → Web Service → connetti repo → Root/Context `backend` → Dockerfile `backend/Dockerfile` (o `Dockerfile.api`).
3. **Worker** (consigliato se usi Redis buffer): New → Background Worker → stesso repo → `backend/Dockerfile.worker`.
4. **Frontend**: New → Static Site → `frontend`, build `npm ci && npm run build`, publish `dist`.

---

## D. Variabili d’ambiente (backend)

### Obbligatorie (produzione)

| Variabile | Note |
|-----------|------|
| `SECRET_KEY` | Stringa lunga casuale |
| `DATABASE_URL` | Su Render spesso Postgres (`postgresql+asyncpg://...`) |
| `FRONTEND_URL` | URL pubblico del sito statico (CORS) |
| `CORS_EXTRA_ORIGINS` | Domini aggiuntivi separati da virgola (es. `www.`) |
| `ALLOWED_HOSTS` | Es. `api.tuodominio.it,*.onrender.com` — evitare `*` in prod se possibile |
| `ENVIRONMENT` | `production` (disabilita `/docs`) |

### Stripe / email

Come da `.env.example` se usi pagamenti e reset mail.

### Telegram

| Variabile | Note |
|-----------|------|
| `TELEGRAM_BOT_TOKEN` | Da BotFather |
| `TELEGRAM_BOT_USERNAME` | Senza `@` |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | Opzionale ma consigliato: **stesso** valore in `setWebhook?secret_token=` |
| `TELEGRAM_WEBHOOK_STRICT_SECRET` | `true` solo dopo aver allineato webhook e env |

### Live / RAM

| Variabile | Default | Significato |
|-----------|---------|-------------|
| `SCRAPER_USE_EVOLUTION_API` | `1` | Usa API JSON leggera |
| `SCRAPER_PLAYWRIGHT_FALLBACK` | `1` | `0` per disattivare Chromium nel processo API |
| `LIVE_ROWS_FROM_REDIS` | `0` | `1` = priorità al buffer Redis del worker |
| `REDIS_URL` | — | Obbligatorio per cache pubblica + worker |
| `PUBLIC_INGESTION_ENABLED` | `1` | `0` disabilita loop ingestione in background |
| `LIVE_WORKER_POLL_SECONDS` | `4` | Solo worker |

### Frontend

- `VITE_API_URL` = URL HTTPS del backend (es. `https://crazy-brain-api.onrender.com`).

---

## E. Domini custom e CORS

1. Nel pannello Render, associa dominio al **static** (es. `www.example.com`) e al **web** (es. `api.example.com`).
2. Imposta `FRONTEND_URL=https://www.example.com` e `CORS_EXTRA_ORIGINS` con eventuali alias (`https://example.com`).
3. `ALLOWED_HOSTS` deve includere l’host API usato dal client.

---

## F. Telegram — webhook

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<API_HOST>/api/notify/telegram/webhook&secret_token=<TELEGRAM_WEBHOOK_SECRET_TOKEN>
```

Verifica con `getWebhookInfo`. Flusso OTP/collegamento: README in root + sezione sicurezza sotto.

---

## G. Redis — cosa contiene

- Chiave cache pubblica (modulo `external_public_cache.py`): payload JSON dashboard.
- Chiave righe live (`live_rows_redis.py`): snapshot lista round Evolution.

Se `REDIS_URL` manca, la cache pubblica torna in-process (più RAM sul dyno API).

---

## H. Monitoring e log

- Cerca `_worker_debug` e `source=` nei log per capire se la sorgente è `redis-live-buffer`, `evolution-api` o Playwright.
- Payload API: `source_latest_settled_utc` (UTC), `source_lag_seconds`, `source_ok`, `source_error`.
- Eventi scartati dal brain: log `public ingest: scarto riga non valida`.

---

## I. Healthcheck e startup

- `/health` non deve dipendere da scrape: resta leggero.
- Il loop pubblico parte dopo ~15s (`PUBLIC_INGESTION_ENABLED`) per non competere con il binding della porta su Render.

---

## J. Checklist pre go-live

- [ ] `GET /health` 200 dal browser esterno.
- [ ] Login / registrazione e CORS dal dominio reale.
- [ ] `GET /api/brain/auto-brain-public` con `source_ok: true` e `source_latest_settled_utc` recente.
- [ ] Confronto manuale ultimi N round con la fonte ufficiale (limitazione: API terza parte).
- [ ] Telegram: `/start` con token → nessun 403; OTP se usato.
- [ ] Stripe webhook (se attivo) con firma valida.
- [ ] Redis: hit su chiavi attese (Dashboard Redis / `redis-cli`).
- [ ] Metriche memoria: sotto soglia OOM; se no → piano superiore o `Dockerfile.api` + worker.
- [ ] `ENVIRONMENT=production` e assenza di stack trace nelle risposte 500 generiche.

---

## K. Sicurezza (sintesi)

- Rate limit già presente (`slowapi`); OTP e auth: non enumerare account (verificare messaggi errore).
- CORS ristretto ai domini reali.
- Nessun secret in repo; ruotare token esposti.
- Header di sicurezza in `main.py` (CSP, HSTS, ecc.) — rivedere `connect-src` se stringi domini API.

---

## L. Limiti dichiarati

- **Correttezza dati al 100%** rispetto al tavolo reale non è garantibile senza feed ufficiale Evolution firmato: dipendiamo da JSON/HTML di terze parti.
- Il codice attuale allinea **slot ruota vs moltiplicatore Top Slot** nel brain solo quando `slot_segment == wheel_segment` e il moltiplicatore Top Slot è noto (`top_slot_multiplier`), riducendo i mismatch precedenti.
