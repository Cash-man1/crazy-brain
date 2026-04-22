# Crazy Brain

Guida semplice semplice per avviare il progetto in locale su Windows.

Se non sei pratico: segui i passaggi in ordine e funziona.

---

## 1) Cosa installare prima

Ti servono solo queste cose:

- **Windows 10/11**
- **Git**: [https://git-scm.com](https://git-scm.com)
- **Node.js LTS**: [https://nodejs.org](https://nodejs.org)
- **Python 3.10+**: [https://www.python.org](https://www.python.org)

Quando installi Python, spunta **Add Python to PATH**.

---

## 2) Scarica il progetto

Apri PowerShell nella cartella dove tieni i progetti e incolla:

```powershell
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

---

## 3) Primo avvio (solo una volta)

Nella cartella del progetto, fai doppio clic su:

`setup.bat`

Aspetta che finisca.

Cosa fa:

- prepara Python (`.venv`)
- installa pacchetti backend
- installa pacchetti frontend
- crea file `.env` base se mancano

---

## 4) Avvio normale (ogni volta)

Fai doppio clic su:

`avvio.bat`

Si aprono due finestre:

- backend su `http://127.0.0.1:8000`
- frontend su `http://localhost:5173`

Poi apri nel browser:

`http://localhost:5173/dashboard`

---

## 5) Controllo veloce (30 secondi)

Per capire se tutto e ok:

1. Apri `http://127.0.0.1:8000/health`
2. Deve rispondere con stato `healthy`
3. Apri `http://localhost:5173/dashboard`
4. Deve caricarsi la dashboard

---

## 6) Se non parte (soluzioni rapide)

### Errore Python non trovato

- reinstalla Python 3.10+
- durante installazione attiva **Add Python to PATH**
- rilancia `setup.bat`

### Errore npm / node

- installa Node.js LTS
- rilancia `setup.bat`

### Frontend aperto ma senza dati

- verifica che backend sia acceso
- controlla `http://127.0.0.1:8000/health`
- controlla file `frontend/.env`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

### Porta occupata

- chiudi vecchie finestre terminale del progetto
- chiudi eventuali vecchi `uvicorn` o `node`
- rilancia `avvio.bat`

---

## 7) Dove salva i dati locali

File utili in locale:

- `backend/public_history.json`
- `backend/public_patterns.json`

Sono dati locali del tuo PC.

---

## 8) Nota su sorgente dati

Di default `avvio.bat` usa:

- API Evolution (`SCRAPER_USE_EVOLUTION_API=1`)
- fallback Playwright se serve (`SCRAPER_PLAYWRIGHT_FALLBACK=1`)

Se vuoi forzare sola lettura HTML, in `avvio.bat` metti:

`SCRAPER_USE_EVOLUTION_API=0`
