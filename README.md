# Crazy Brain

Applicazione web per **analisi e segnali** su Crazy Time (casino live): **frontend** in `frontend/`, **backend** API in `backend/`.

Può inviare **notifiche segnali** su **Telegram** tramite bot (config in `backend/.env`, senza login nell’app).

---

## Indice (parti da qui se non sai da dove iniziare)

1. [Prima volta sul PC (Windows)](#1-prima-volta-sul-pc-windows) — far partire l’app in locale  
2. [Telegram: segnali senza login nell’app](#2-telegram-segnali-senza-login-nellapp) — bot, `.env`, notifiche  
3. [Usare l’app nel browser](#3-usare-lapp-nel-browser) — dashboard e `/connect`  
4. [Pubblicare su GitHub e Render](#4-pubblicare-su-github-e-render)  
5. [Note su dati e sicurezza](#5-note-su-dati-e-sicurezza)

---

## 1) Prima volta sul PC (Windows)

### Cosa ti serve installato

- **Windows 10/11**
- **Git** (per scaricare il progetto): [https://git-scm.com](https://git-scm.com)  
- **Node.js** (LTS): [https://nodejs.org](https://nodejs.org) — serve per il frontend  
- **Python 3.10+**: [https://www.python.org](https://www.python.org) — durante `setup.bat` conviene avere “Add Python to PATH” spuntato

### Scarica il progetto

Apri **PowerShell** o **Prompt dei comandi**, vai nella cartella dove tieni i progetti, poi:

```powershell
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

(Se il tuo fork ha un altro URL, usa quello.)

### Una sola volta: `setup.bat`

Nella cartella del progetto (`crazy-brain` o come l’hai rinominata):

1. Doppio clic su **`setup.bat`**  
   oppure da terminale, nella cartella del repo: `.\setup.bat`

Cosa fa in sintesi: crea l’ambiente Python **`.venv`**, installa le dipendenze backend, opzionalmente **Playwright Chromium**, esegue **`npm ci`** nel frontend, e crea file **`.env`** di esempio se mancano (`backend\.env`, `frontend\.env`).

### Ogni volta che vuoi lavorare: `avvio.bat`

Doppio clic su **`avvio.bat`**.

Si aprono di solito **due finestre**:

- **Backend** → API su `http://127.0.0.1:8000` (controlla che risponda: apri `http://127.0.0.1:8000/health` nel browser)  
- **Frontend** → sito Vite su `http://localhost:5173`

`avvio.bat` imposta anche variabili utili (es. **72 ore** di cronologia casino per Playwright, storico fino a **5000** giocate in locale). Per modificarle, apri `avvio.bat` con un editor di testo.

---

## 2) Telegram: segnali senza login nell’app

L’interfaccia **non** usa più form di login/registrazione per i segnali: configuri il **bot** e i **chat id** nel `backend/.env`. Nella dashboard apri **`/connect`** per la guida testuale.

| Cosa | Note |
|------|------|
| **Segnali caldi** | `NOTIFY_SIGNALS_ENABLED=true` + token bot + `TELEGRAM_CHAT_IDS` (vedi sotto) |
| **Solo alcuni segmenti** (broadcast `.env`) | Opzionale: `NOTIFY_BROADCAST_SEGMENTS=1,2,CH` |
| **Webhook HTTPS** | Solo se usi ancora flussi OTP/utenti DB; **non** serve solo per `TELEGRAM_CHAT_IDS` |

### Passo A — Crea il bot (una volta)

1. Apri Telegram e cerca **`@BotFather`**  
2. Invia `/newbot` e segui le istruzioni (nome e username del bot)  
3. BotFather ti dà il **token** (lungo, segreto: non condividerlo, non metterlo su GitHub)  
4. Annota anche lo **username** del bot (es. `MioCrazyBrainBot`, **senza** `@`)

### Passo B — Metti il bot nel file di configurazione del backend

1. Nella cartella `backend`, copia il modello se non hai ancora un file tuo:  
   - copia `backend\.env.example` → rinomina in **`backend\.env`** (se non esiste già)  
2. Apri **`backend\.env`** con Blocco note o VS Code e imposta almeno:

```env
TELEGRAM_BOT_TOKEN=il_token_che_ti_ha_dato_botfather
TELEGRAM_BOT_USERNAME=nome_utente_bot_senza_chiocciola
NOTIFY_SIGNALS_ENABLED=true
NOTIFY_MIN_CONFIDENCE=0.45
TELEGRAM_CHAT_IDS=IL_TUO_CHAT_ID
# Opzionale: solo questi segmenti verso TELEGRAM_CHAT_IDS
# NOTIFY_BROADCAST_SEGMENTS=1,2,CH
```

Salva il file. **Riavvia** il backend (`avvio.bat` o il terminale dove gira `uvicorn`) dopo ogni modifica a `.env`.

**Chat id:** chiedilo a bot come `@userinfobot` o `@getidsbot` su Telegram. In `frontend/.env`, `VITE_TELEGRAM_BOT_USERNAME` (senza `@`) mostra il pulsante “Apri bot” in `/connect`.

### Passo C — Webhook (solo se usi OTP / utenti in database)

Se ti serve collegare la chat a un utente nel DB con `/start`, serve HTTPS e `setWebhook` verso  
`https://<TUO_BACKEND>/api/notify/telegram/webhook` — vedi **[docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md)**.

### Passo D — (Opzionale) API login telefono

Le route backend per OTP/login restano; in questa versione **non** c’è pagina login nel frontend (solo dashboard + `/connect` guida).

---

## 3) Usare l’app nel browser

- **Dashboard pubblica (senza login)** — tipicamente:  
  `http://localhost:5173/dashboard`  
  Mostra ultimi esiti, mini cervelli, statistiche live (secondo configurazione API pubblica).

- **`/connect`** — guida per configurare il bot Telegram e le variabili `.env` (nessun form di login).

Se il frontend non parla col backend, controlla **`frontend\.env`**: deve esserci qualcosa come `VITE_API_URL=http://127.0.0.1:8000`.

---

## 4) Pubblicare su GitHub e Render

### GitHub

```powershell
git status
git add .
git commit -m "descrizione delle modifiche"
git push origin main
```

**Non committare mai** `backend\.env` con token veri (è in `.gitignore`). Usa solo `.env.example` come modello.

### Render (hosting)

- Blueprint: **`render.yaml`** nel repo  
- Guida dettagliata: **[docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md)** (servizi, Redis, worker, variabili, checklist)

Variabili Telegram lato backend (Render), in sintesi:

- `NOTIFY_SIGNALS_ENABLED=true`  
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`  
- `TELEGRAM_CHAT_IDS` (opzionale, CSV di chat id)  
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` + `setWebhook` allineato (consigliato in produzione)

Frontend su Render:

- `VITE_API_URL` = URL pubblico del backend (es. `https://tuo-api.onrender.com`)

### Render free e “sempre acceso”

Su piano gratuito il servizio può andare in **sleep**. Soluzioni: piano a pagamento, oppure servizi esterni che chiamano periodicamente `GET <BACKEND_URL>/health`.

---

## 5) Note su dati e sicurezza

- **Cronologia / pattern in locale** (desktop): file tipo `backend/public_history.json` e `backend/public_patterns.json` (vedi `.gitignore`: di solito non vanno su GitHub).  
- **In produzione** imposta sempre `SECRET_KEY` lungo e unico nel `.env` / pannello Render — non usare mai il placeholder di esempio in produzione.  
- **Admin / VIP di seed**: il repository **non** contiene password preimpostate per account demo; se vuoi un admin iniziale, imposta `ADMIN_EMAIL` e `ADMIN_PASSWORD` nel `.env` (password che rispetti la lunghezza minima del progetto).

---

## Dove approfondire

| Argomento | File |
|-----------|------|
| Deploy Render, Redis, worker | [docs/RENDER_DEPLOY.md](docs/RENDER_DEPLOY.md) |
| Variabili ambiente modello | `backend/.env.example` |
| URL API Telegram (setWebhook) | [documentazione ufficiale](https://core.telegram.org/bots/api#setwebhook) |

---

## Sviluppo desktop: sorgente dati (richiamo)

- Con **`SCRAPER_USE_EVOLUTION_API=1`** (default in `avvio.bat`) si usano gli ultimi round da API JSON (leggero).  
- Con **`SCRAPER_PLAYWRIGHT_FALLBACK=1`**, se l’API non risponde, si usa Playwright sulla pagina `casino.org` (serve Chromium da `setup.bat`).  
- **Solo HTML**: in `avvio.bat` imposta `SCRAPER_USE_EVOLUTION_API=0`.

In produzione su Render la logica privilegia di solito API + Redis/worker; in locale `avvio.bat` ti dà un flusso simile con fallback browser se serve.
