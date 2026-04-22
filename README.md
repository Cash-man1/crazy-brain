# Crazy Brain

Applicazione web locale per analisi e segnali su Crazy Time.
Stack: frontend in `frontend/`, backend API in `backend/`.

---

## Avvio rapido (Windows)

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
## Uso nel browser

- **Dashboard** — tipicamente:  
  `http://localhost:5173/dashboard`  
  Mostra ultimi esiti, mini cervelli e statistiche live.

Se il frontend non parla col backend, controlla **`frontend\.env`**: deve esserci qualcosa come `VITE_API_URL=http://127.0.0.1:8000`.

---
## Note dati e sicurezza

- **Cronologia / pattern in locale** (desktop): file tipo `backend/public_history.json` e `backend/public_patterns.json` (vedi `.gitignore`: di solito non vanno su GitHub).  
- **In produzione** imposta sempre `SECRET_KEY` lungo e unico nel `.env` / pannello Render — non usare mai il placeholder di esempio in produzione.  
- **Admin / VIP di seed**: il repository **non** contiene password preimpostate per account demo; se vuoi un admin iniziale, imposta `ADMIN_EMAIL` e `ADMIN_PASSWORD` nel `.env` (password che rispetti la lunghezza minima del progetto).

---
## Sviluppo desktop: sorgente dati (richiamo)

- Con **`SCRAPER_USE_EVOLUTION_API=1`** (default in `avvio.bat`) si usano gli ultimi round da API JSON (leggero).  
- Con **`SCRAPER_PLAYWRIGHT_FALLBACK=1`**, se l’API non risponde, si usa Playwright sulla pagina `casino.org` (serve Chromium da `setup.bat`).  
- **Solo HTML**: in `avvio.bat` imposta `SCRAPER_USE_EVOLUTION_API=0`.
