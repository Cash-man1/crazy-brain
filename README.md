# Crazy Brain

Questa è una web app con:
- **Frontend** (il sito): cartella `frontend/`
- **Backend** (le API): cartella `backend/`

L’app mostra **segnali** e può inviare messaggi su **Telegram**:
- **OTP su Telegram (gratis)** per registrazione e reset password
- **Notifiche segnali (opzionali)** su Telegram (scegli tu i segmenti)

---

## Come funziona (spiegato semplice)

### Registrazione con telefono (OTP su Telegram)
1) Vai su `Login` → scegli **Phone** → inserisci il numero (es. `+39...`)  
2) Clicca **“Collega Telegram (obbligatorio)”**  
3) Si apre un link del bot → su Telegram premi **START**  
4) Torna in app e clicca **“Invia OTP su Telegram”**  
5) Inserisci OTP + password → account creato  
6) Da quel momento fai login con **numero + password**

### Importante
- Premere **START** sul bot **NON** attiva le notifiche segnali.
- Le notifiche segnali si attivano solo nella pagina **`/connect`**.

### Password dimenticata (telefono)
Vai su **`/phone-forgot-password`** e fai:
numero → collega Telegram → invia OTP → inserisci OTP → nuova password.

---

## Pubblicare online (GitHub + Render) — passi facili
Ti servono:
- un account **GitHub**
- un account **Render**
- un bot **Telegram** (gratis, via BotFather)

---

## 1) Caricare su GitHub
Apri PowerShell nella cartella del progetto e fai:

```powershell
git status
git add .
git commit -m "deploy: crazy brain"
git push origin main
```

---

## 2) Deploy su Render (automatico con `render.yaml`)
1) Vai su Render  
2) **New → Blueprint**  
3) Collega il repo GitHub  
4) Il Blueprint crea i servizi con questi ruoli (vedi tabella estesa in **`docs/RENDER_DEPLOY.md`**):
   - **`crazy-brain-web`** — frontend statico (sito)
   - **`crazy-brain-api`** — API leggera (Docker backend)
   - **`crazy-brain-live-worker`** — worker separato per dati live (httpx → Redis)
   - Aggiungi un **Redis** (Render o Upstash) e imposta **`REDIS_URL`** su API + worker: cache pubblica dashboard + buffer righe live (consigliato)

### Variabili (ENV) da impostare su Render

#### Backend (`crazy-brain-api`)
- `FRONTEND_URL` = URL del frontend (su Render o `https://crazy-brain.it`)
- `CORS_EXTRA_ORIGINS` = (opzionale) altri domini separati da virgola
- `ALLOWED_HOSTS` = `api.crazy-brain.it,localhost,127.0.0.1,*.onrender.com`
- `NOTIFY_SIGNALS_ENABLED` = `true`
- `TELEGRAM_BOT_TOKEN` = token del bot
- `TELEGRAM_BOT_USERNAME` = username bot (senza `@`)
- `TELEGRAM_CHAT_IDS` = (opzionale) uno o più **chat id** separati da virgola: ricevi i segnali **senza** account DB (utile per dashboard pubblica locale)
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` = (opzionale) stesso valore che passi a `setWebhook` come `secret_token`
- `TELEGRAM_WEBHOOK_STRICT_SECRET` = `true` solo se vuoi **rifiutare** richieste senza header secret (vedi sotto)

#### Frontend (`crazy-brain-web`)
- `VITE_API_URL` = URL pubblico del backend (es. `https://crazy-brain-api.onrender.com`)

---

## Deploy Render (guida completa)

Vedi **[docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md)** (servizi, env, Redis, worker, domini, checklist).

---

## 3) Telegram bot (creazione + webhook)

### Crea bot
Su Telegram apri **BotFather**, poi:
- crea il bot
- copia il **token**
- salva lo **username** del bot

### Imposta webhook
Quando il backend è online, l’URL del webhook deve essere:

`https://<BACKEND_URL>/api/notify/telegram/webhook`

**Importante:** se imposti `TELEGRAM_WEBHOOK_SECRET_TOKEN` su Render, Telegram manda l’header `X-Telegram-Bot-Api-Secret-Token` **solo** se registri il webhook con lo stesso `secret_token` ([documentazione Telegram](https://core.telegram.org/bots/api#setwebhook)). Esempio (sostituisci token, URL e secret):

`https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https%3A%2F%2F<host>%2Fapi%2Fnotify%2Ftelegram%2Fwebhook&secret_token=<STESSO_VALORE_DI_TELEGRAM_WEBHOOK_SECRET_TOKEN>`

- Se il webhook era stato registrato **senza** `secret_token` ma in env c’è il secret, il backend rispondeva **403** (header assente). Ora, con `TELEGRAM_WEBHOOK_STRICT_SECRET=false` (default), le richieste senza header sono accettate ma conviene allineare `setWebhook` + env oppure impostare `TELEGRAM_WEBHOOK_STRICT_SECRET=true` dopo aver configurato correttamente il secret su Telegram.

---

## Render “sempre acceso” (spiegato facile)
Su **Render Free** il backend può andare in sleep.
Per tenerlo sempre attivo:
- **piano a pagamento** su Render (soluzione migliore)
oppure
- **UptimeRobot** (gratis) che chiama `GET <BACKEND_URL>/health` ogni 5 minuti

---

## Sviluppo desktop (Windows) — `setup.bat` + `avvio.bat`

Per usare Crazy Brain **in locale** come prima (backend + frontend, ultimi esiti / orari dalla stessa logica di produzione):

1. Doppio clic o da terminale: **`setup.bat`** (una volta) — crea `.venv`, installa backend + Playwright Chromium + `npm ci` nel frontend, crea `backend\.env` e `frontend\.env` se mancano.
2. Poi: **`avvio.bat`** — apre due finestre: API su `http://127.0.0.1:8000` e Vite (di solito `http://localhost:5173`).

Impostazioni predefinite in `avvio.bat`:

- **`SCRAPER_USE_EVOLUTION_API=1`** — stessa API JSON usata in produzione (ultimi round, orari coerenti, leggero).
- **`SCRAPER_PLAYWRIGHT_FALLBACK=1`** — se l’API non risponde, usa Playwright sulla pagina `casino.org` (serve Chromium installato da `setup.bat`).

Se vuoi **solo** la lettura della pagina HTML (niente API): in `avvio.bat` imposta `SCRAPER_USE_EVOLUTION_API=0`.

**Cronologia casino (Playwright):** in `avvio.bat` c’è `SCRAPER_CRONOLOGIA_HOURS` (default **`72`**) per allineare il lasso temporale al menu del sito. **Storico salvato in locale:** finestra scorrevole delle ultime `PUBLIC_HISTORY_MAX_ITEMS` (default **5000**) in `backend/public_history.json` — le nuove giocate si aggiungono sempre; superata la soglia, le più vecchie vengono scartate dal file. I **pattern** restano in `backend/public_patterns.json` e si ricaricano al riavvio.

I file `.bat` sono **nel repository** così il flusso desktop è ripetibile anche dopo clone da GitHub.

---

## Nota su casino.org e produzione
In produzione su Render la dashboard usa soprattutto l’**API Evolution** (e opzionalmente Redis/worker), non il browser sul sito `casino.org`. **In locale**, con `avvio.bat`, puoi comunque avere il fallback Playwright sulla pagina reale se l’API fallisce.
