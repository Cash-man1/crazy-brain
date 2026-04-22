🧠 Crazy Brain
Guida semplice (Windows + macOS)
🪟 WINDOWS
🧩 1. Installa i programmi

Scarica e installa:

Git → https://git-scm.com/download/win
Node.js (LTS) → https://nodejs.org/en/download
Python 3.10+ → https://www.python.org/downloads/windows/

⚠️ Durante installazione Python → ✔️ Add to PATH

💻 2. Apri il terminale

👉 Cerca nel menu Start:

cmd
oppure PowerShell
oppure Terminale Windows
📥 3. Scarica il progetto

Nel terminale incolla:

git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
📁 4. Apri la cartella

👉 Vai nella cartella crazy-brain appena scaricata

⚙️ 5. Setup (prima volta)

👉 Fai doppio clic su:

setup.bat

⏳ Aspetta qualche minuto

▶️ 6. Avvio

👉 Fai doppio clic su:

avvio.bat

👉 Poi apri nel browser:

http://localhost:5173/dashboard
⛔ 7. Chiusura

👉 Fai doppio clic su:

chiudi.bat
🍎 macOS
💻 1. Apri il Terminale

👉 Premi:

CMD + SPACE

Scrivi:

Terminal
📥 2. Scarica il progetto
git clone https://github.com/Cash-man1/crazy-brain.git
cd crazy-brain
⚙️ 3. Setup (prima volta)
chmod +x setup-mac.sh avvio-mac.sh chiudi-mac.sh
./setup-mac.sh
▶️ 4. Avvio
./avvio-mac.sh

👉 Apri nel browser:

http://localhost:5173/dashboard
⛔ 5. Chiusura
./chiudi-mac.sh
🧯 SE QUALCOSA NON FUNZIONA
❌ Pagina non si apre

👉 Controlla:

http://127.0.0.1:8000/health
❌ Non parte nulla

👉 Rifai setup:

Windows:

setup.bat

Mac:

./setup-mac.sh
❌ Errori strani

👉 Soluzione universale:

Chiudi tutto
Rifai setup
Riavvia
🚀 FATTO

Se vedi la dashboard → funziona 🎉
