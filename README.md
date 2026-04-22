# Crazy Brain

Guida super semplice per usare Crazy Brain su Windows.

Questa guida dice solo:

- cosa installare
- come installarlo
- come avviare il programma

Niente parti tecniche da sviluppatore.

---

## 1) Cosa devi installare (Windows)

Installa queste 3 cose, in questo ordine:

1. **Git**: [https://git-scm.com/download/win](https://git-scm.com/download/win)
2. **Node.js LTS**: [https://nodejs.org/en/download](https://nodejs.org/en/download)
3. **Python 3.10+**: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)

Quando installi Python:

- metti la spunta su **Add Python to PATH**
- poi fai **Install Now**

Quando installi Git e Node.js:

- lascia le opzioni di default
- clicca sempre **Next** fino a **Finish**

---

## 2) Scarica il progetto

Apri PowerShell e incolla:

```powershell
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

---

## 3) Primo setup (una sola volta)

Apri la cartella del progetto e fai doppio clic su:

`setup.bat`

Aspetta la fine completa. Non chiudere le finestre durante il setup.

---

## 4) Avvio dell'app (ogni volta)

Fai doppio clic su:

`avvio.bat`

Si aprono due finestre:

- backend su `http://127.0.0.1:8000`
- frontend su `http://localhost:5173`

Quando parte, apri questo link nel browser:

`http://localhost:5173/dashboard`

---

## 5) Stop dell'app

Per chiudere tutto in modo pulito:

- fai doppio clic su `chiudi.bat`

---

## 6) Guida visuale rapida (screen da seguire)

- **Schermata 1:** cartella progetto aperta
- **Schermata 2:** doppio clic su `setup.bat` (solo la prima volta)
- **Schermata 3:** doppio clic su `avvio.bat`
- **Schermata 4:** browser su `http://localhost:5173/dashboard`

---

## 7) Se non va (soluzione veloce)

### Caso A - Non parte nulla

- riavvia il PC
- riesegui `setup.bat`
- poi riesegui `avvio.bat`

### Caso B - Errore Python

- reinstalla Python da [python.org](https://www.python.org/downloads/windows/)
- spunta **Add Python to PATH**
- rifai `setup.bat`

### Caso C - Errore Node / npm

- reinstalla Node.js LTS da [nodejs.org](https://nodejs.org/en/download)
- rifai `setup.bat`

### Caso D - Si apre ma non carica

- chiudi con `chiudi.bat`
- riapri con `avvio.bat`
- aspetta 20-30 secondi e ricarica la pagina

Se ancora non va, rifai da capo i passi 1 -> 4.
