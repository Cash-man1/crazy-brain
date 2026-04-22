# Crazy Brain

Guida veloce per usare Crazy Brain su **macOS** in modo plug-and-play.

---

## 1) Installa queste cose (una volta)

- **Git**: [https://git-scm.com/download/mac](https://git-scm.com/download/mac)
- **Node.js LTS**: [https://nodejs.org/en/download](https://nodejs.org/en/download)
- **Python 3.10+**: [https://www.python.org/downloads/macos/](https://www.python.org/downloads/macos/)

Alternativa comoda:

```bash
brew install git node python
```

---

## 2) Scarica il progetto

Apri Terminale e incolla:

```bash
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
```

---

## 3) Primo setup Mac (una sola volta)

```bash
chmod +x setup-mac.sh avvio-mac.sh chiudi-mac.sh
./setup-mac.sh
```

---

## 4) Avvio Mac (ogni volta)

```bash
./avvio-mac.sh
```

Poi apri:

`http://localhost:5173/dashboard`

---

## 5) Chiusura Mac

```bash
./chiudi-mac.sh
```

---

## 6) Se non parte

- rifai setup: `./setup-mac.sh`
- poi riavvia: `./avvio-mac.sh`
- controlla backend: `http://127.0.0.1:8000/health`
