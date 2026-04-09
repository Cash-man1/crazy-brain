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
4) Render crea 2 servizi:
   - **`crazy-brain-api`** (backend)
   - **`crazy-brain-web`** (frontend)

### Variabili (ENV) da impostare su Render

#### Backend (`crazy-brain-api`)
- `FRONTEND_URL` = URL del frontend (su Render o `https://crazy-brain.it`)
- `CORS_EXTRA_ORIGINS` = (opzionale) altri domini separati da virgola
- `ALLOWED_HOSTS` = `api.crazy-brain.it,localhost,127.0.0.1,*.onrender.com`
- `NOTIFY_SIGNALS_ENABLED` = `true`
- `TELEGRAM_BOT_TOKEN` = token del bot
- `TELEGRAM_BOT_USERNAME` = username bot (senza `@`)
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` = una stringa a tua scelta (consigliato)

#### Frontend (`crazy-brain-web`)
- `VITE_API_URL` = URL pubblico del backend (es. `https://crazy-brain-api.onrender.com`)

---

## 3) Telegram bot (creazione + webhook)

### Crea bot
Su Telegram apri **BotFather**, poi:
- crea il bot
- copia il **token**
- salva lo **username** del bot

### Imposta webhook
Quando il backend è online, imposta il webhook così:

`https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<BACKEND_URL>/api/notify/telegram/webhook`

---

## Render “sempre acceso” (spiegato facile)
Su **Render Free** il backend può andare in sleep.
Per tenerlo sempre attivo:
- **piano a pagamento** su Render (soluzione migliore)
oppure
- **UptimeRobot** (gratis) che chiama `GET <BACKEND_URL>/health` ogni 5 minuti

---

## Nota importante su casino.org
In produzione su Render **nessuno vedrà** la pagina `casino.org`.
Quella era una cosa solo locale (gli script locali non vengono caricati su GitHub).
