# Crazy Brain

Applicazione web per **analisi e segnali** su Crazy Time (casino live): **frontend** in `frontend/`, **backend** API in `backend/`.

Può inviare avvisi su **Telegram** (OTP per account telefono, e opzionalmente **notifiche segnali**).

---

## Indice (parti da qui se non sai da dove iniziare)

1. [Prima volta sul PC (Windows)](#1-prima-volta-sul-pc-windows) — far partire l’app in locale  
2. [Telegram: cosa serve e in che ordine](#2-telegram-cosa-serve-e-in-che-ordine) — bot, webhook, `.env`, notifiche  
3. [Usare l’app nel browser](#3-usare-lapp-nel-browser) — dashboard pubblica vs account  
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

## 2) Telegram: cosa serve e in che ordine

Telegram viene usato per **due cose diverse**. Convince se le separi mentalmente:

| Cosa | A cosa serve | Serve il webhook? |
|------|----------------|---------------------|
| **OTP / collegamento account** | Registrazione o login con **numero di telefono**: ricevi il codice sul bot | **Sì** — Telegram deve poter chiamare il tuo backend |
| **Notifiche segnali** | Messaggi tipo “segnale su segmento X” quando il cervello trova qualcosa di caldo | **No** per l’invio (il server chiama Telegram); il webhook serve solo se vuoi che l’utente **colleghi** la chat dall’app con `/start` |

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
```

Salva il file. **Riavvia** il backend (`avvio.bat` o il terminale dove gira `uvicorn`) dopo ogni modifica a `.env`.

### Passo C — Webhook (obbligatorio per “Collega Telegram” nell’app)

Il backend deve essere **raggiungibile da Internet** con un URL **HTTPS** (in locale spesso usi **ngrok** o simili; su Render hai già l’HTTPS).

L’URL del webhook è sempre questo path sul **tuo** dominio API:

`https://<TUO_BACKEND_PUBBLICO>/api/notify/telegram/webhook`

**Esempio** (sostituisci `TOKEN`, `HOST` e opzionalmente `SECRET`):

```text
https://api.telegram.org/botTOKEN/setWebhook?url=https%3A%2F%2FHOST%2Fapi%2Fnotify%2Ftelegram%2Fwebhook&secret_token=SECRET
```

- Incolla l’URL completo nel **browser** oppure usa curl.  
- Se usi `secret_token`, metti **lo stesso valore** in `backend\.env` come `TELEGRAM_WEBHOOK_SECRET_TOKEN`.  
- Se Telegram non manda l’header del secret, con `TELEGRAM_WEBHOOK_STRICT_SECRET=false` (default nel progetto) il backend accetta comunque; in produzione conviene allineare bene secret e webhook.

Dopo il `setWebhook`, in Telegram apri il bot e prova **START** dal link che genera l’app (vedi sotto): se il webhook è giusto, il backend riesce a salvare il tuo **chat id** sul profilo utente.

### Passo D — Due modi per ricevere i **segnali** su Telegram

**Modo 1 — Sei registrato nell’app (consigliato se usi login)**

1. Avvia backend + frontend  
2. Accedi all’app (account con telefono + password, dopo OTP)  
3. Vai alla pagina **`/connect`** (menu “Collega Telegram / preferenze segnali” se presente)  
4. Genera il link, aprilo in Telegram, premi **START** (questo collega la **chat** al tuo account)  
5. Nell’app attiva le notifiche e scegli i **segmenti** che ti interessano  

Il backend invia solo se in `.env` hai anche:

```env
NOTIFY_SIGNALS_ENABLED=true
NOTIFY_MIN_CONFIDENCE=0.45
```

(`NOTIFY_MIN_CONFIDENCE` è la soglia minima di “confidence” per spedire; puoi alzarla o abbassarla.)

**Modo 2 — Solo file `.env` (utile per dashboard pubblica in locale, senza DB utente)**

Aggiungi in **`backend\.env`**:

```env
NOTIFY_SIGNALS_ENABLED=true
TELEGRAM_CHAT_IDS=123456789
```

- `123456789` è un **esempio**: al suo posto metti il **tuo chat id** (numero intero come stringa).  
- Più chat: separa con virgola, es. `111111111,222222222`.  
- Per scoprire il tuo id: scrivi a bot come `@userinfobot` o `@getidsbot` su Telegram, oppure guarda i log quando fai START sul tuo bot (se hai logging attivo).

In questo modo il server manda i segnali caldi anche **senza** aver creato l’utente collegato in database.

### Passo E — Registrazione telefono + OTP (richiede bot + webhook)

1. Vai su **Login** → modalità **telefono**  
2. **Collega Telegram** (obbligatorio per ricevere OTP)  
3. Apri il link → **START** sul bot  
4. Torna in app → **Invia OTP su Telegram**  
5. Inserisci OTP e scegli password  

**Nota:** premere START sul bot **da solo** **non** attiva le notifiche segnali: per quelle serve **`/connect`** o `TELEGRAM_CHAT_IDS` come sopra.

---

## 3) Usare l’app nel browser

- **Dashboard pubblica (senza login)** — tipicamente:  
  `http://localhost:5173/dashboard`  
  Mostra ultimi esiti, mini cervelli, statistiche live (secondo configurazione API pubblica).

- **Funzioni con account** (abbonamento / Stripe / profilo / `/connect`) — segui le route dell’app (es. `/login`, `/connect`).

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
