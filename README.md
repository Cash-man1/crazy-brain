# Crazy Brain

Guida super semplice per usare Crazy Brain su **macOS**.

Questa guida dice solo:

- cosa installare
- come installarlo
- come avviare il programma

Niente parti tecniche da sviluppatore.

---

## 1) Cosa devi installare (Mac)

Installa queste 3 cose, in questo ordine:

1. **Git**: [https://git-scm.com/download/mac](https://git-scm.com/download/mac)
2. **Node.js LTS**: [https://nodejs.org/en/download](https://nodejs.org/en/download)
3. **Python 3.10+**: [https://www.python.org/downloads/macos/](https://www.python.org/downloads/macos/)

Puoi installare anche da Homebrew (consigliato):

```bash
brew install git node python
```

---

## 2) Scarica il progetto

Apri il **Terminale** e incolla:

```bash
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

---

## 3) Primo setup (una sola volta)

Nel Terminale, dentro la cartella `crazy-brain`, esegui:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
cd backend && playwright install chromium && cd ..
cd frontend && npm ci && cd ..
```

Aspetta la fine completa. Non chiudere le finestre durante il setup.

---

## 4) Avvio dell'app (ogni volta)

Apri **2 finestre Terminale** nella cartella `crazy-brain`.

### Terminale 1 (backend)

```bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Terminale 2 (frontend)

```bash
cd frontend
npm run dev
```

Quando parte, apri questo link nel browser:

`http://localhost:5173/dashboard`

---

## 5) Stop dell'app

Per chiudere tutto in modo pulito, in entrambi i terminali premi:

`Ctrl + C`

---

## 6) Guida visuale rapida (Mac)

- **Schermata 1:** Terminale con `git clone ...`
- **Schermata 2:** Terminale con setup completato (venv + pip + npm)
- **Schermata 3:** due terminali aperti (backend + frontend)
- **Schermata 4:** browser su `http://localhost:5173/dashboard`

---

## 7) Se non va (soluzione veloce)

### Caso A - Non parte nulla

- chiudi i terminali
- riapri il Mac
- rifai i passi da 3 a 4

### Caso B - Errore Python

- reinstalla Python da [python.org](https://www.python.org/downloads/macos/)
- oppure: `brew install python`
- rifai il passo 3

### Caso C - Errore Node / npm

- reinstalla Node.js LTS da [nodejs.org](https://nodejs.org/en/download)
- oppure: `brew install node`
- rifai il passo 3

### Caso D - Si apre ma non carica

- controlla backend: `http://127.0.0.1:8000/health`
- se non risponde, riavvia solo il terminale backend
- se risponde, ricarica la dashboard dopo 20-30 secondi

Se ancora non va, rifai da capo i passi 1 -> 4.
