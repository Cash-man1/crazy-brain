# Crazy Brain

Guida veloce plug-and-play per utenti **Windows** e **macOS**.

---

## 1) Scarica il progetto (Windows e Mac)

Apri terminale e incolla:

```bash
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

---

## 2) Windows (plug-and-play)

### Cosa installare

- Git: [https://git-scm.com/download/win](https://git-scm.com/download/win)
- Node.js LTS: [https://nodejs.org/en/download](https://nodejs.org/en/download)
- Python 3.10+: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)

Quando installi Python su Windows, spunta **Add Python to PATH**.

### Primo setup (una volta)

Fai doppio clic su:

`setup.bat`

### Avvio (ogni volta)

Fai doppio clic su:

`avvio.bat`

Poi apri:

`http://localhost:5173/dashboard`

### Chiusura

Fai doppio clic su:

`chiudi.bat`

---

## 3) macOS (plug-and-play)

### Cosa installare

- Git: [https://git-scm.com/download/mac](https://git-scm.com/download/mac)
- Node.js LTS: [https://nodejs.org/en/download](https://nodejs.org/en/download)
- Python 3.10+: [https://www.python.org/downloads/macos/](https://www.python.org/downloads/macos/)

Alternativa (consigliata) con Homebrew:

```bash
brew install git node python
```

### Primo setup (una volta)

```bash
chmod +x setup-mac.sh avvio-mac.sh chiudi-mac.sh
./setup-mac.sh
```

### Avvio (ogni volta)

```bash
./avvio-mac.sh
```

Poi apri:

`http://localhost:5173/dashboard`

### Chiusura

```bash
./chiudi-mac.sh
```

---

## 4) Se non parte (rapido)

- Windows: rifai `setup.bat`, poi `avvio.bat`
- Mac: rifai `./setup-mac.sh`, poi `./avvio-mac.sh`
- controlla backend: `http://127.0.0.1:8000/health`
