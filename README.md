# Crazy Brain SaaS

Applicazione SaaS completa per l'analisi di Crazy Time con sicurezza enterprise-grade.

## 🚀 Caratteristiche

### Sicurezza
- 🔐 Autenticazione JWT con bcrypt (cost factor 12)
- 🛡️ Rate limiting (5 registrazioni/min, 10 login/min)
- 🔒 Headers di sicurezza (HSTS, CSP, X-Frame-Options)
- 📝 Audit logging completo
- 🚫 Protezione XSS, CSRF, SQL Injection
- 🔑 Password policy robusta (8+ chars, numeri, simboli, maiuscole)

### Pagamenti
- 💳 Integrazione Stripe completa
- 🔄 Webhook per sincronizzazione automatica
- 📊 Gestione abbonamenti mensili/annuali
- 🎁 Trial automatico (primi 100 utenti = 2 giorni)

### Tool Crazy Time
- 🧠 Brain Engine con MiniBrains e MetaBrain
- 📈 Analisi EV in tempo reale
- 🔍 Pattern recognition
- 💰 Gestione bankroll professionale
- ⚡ Segnali di entrata

### Admin Dashboard
- 👥 Gestione utenti completa
- 📊 Statistiche in tempo reale
- 🔐 Controllo accessi
- 📝 Audit log

## 📁 Struttura Progetto

```
crazy-brain-saas/
├── backend/              # FastAPI + SQLAlchemy
│   ├── main.py          # Entry point
│   ├── config.py        # Configurazione
│   ├── database.py      # Modelli DB
│   ├── security.py      # Auth & sicurezza
│   ├── brain_engine.py  # Logica Crazy Time
│   ├── api_auth.py      # API autenticazione
│   ├── api_stripe.py    # API pagamenti
│   ├── api_brain.py     # API tool
│   └── api_admin.py     # API admin
│
└── frontend/            # React + TypeScript + Tailwind
    ├── src/
    │   ├── pages/       # Pagine applicazione
    │   ├── contexts/    # Context React
    │   ├── lib/         # API client
    │   └── types/       # Tipi TypeScript
    └── ...
```

## 🛠️ Setup Locale

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Crea file .env
cp .env.example .env
# Modifica le variabili in .env

# Avvia server
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install

# Crea file .env
cp .env.example .env
# Modifica VITE_API_URL

# Avvia dev server
npm run dev
```

## 🚀 Deploy

### Backend (Render)

1. Crea nuovo Web Service su Render
2. Connetti repository GitHub
3. Configura:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Aggiungi Environment Variables da `.env`
5. Deploy!

### Frontend (Render Static Site / Vercel / Netlify)

1. Crea nuovo Static Site su Render
2. Connetti repository GitHub
3. Configura:
   - **Build Command**: `npm run build`
   - **Publish Directory**: `dist`
4. Aggiungi Environment Variables
5. Deploy!

### Stripe Webhook

Configura webhook su Stripe Dashboard:
- **Endpoint**: `https://api.crazy-brain.it/api/stripe/webhook`
- **Events**: `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.updated`, `customer.subscription.deleted`

## 🔐 Variabili d'Ambiente

### Backend (.env)

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./crazybrain.db

# Sicurezza
SECRET_KEY=your-super-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_MONTHLY=price_...
STRIPE_PRICE_ANNUAL=price_...

# Email
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# App
APP_URL=https://crazy-brain.it
FRONTEND_URL=https://crazy-brain.it
ENVIRONMENT=production
```

### Frontend (.env)

```env
VITE_API_URL=https://api.crazy-brain.it
VITE_STRIPE_PUBLISHABLE_KEY=pk_live_...
VITE_APP_URL=https://crazy-brain.it
```

## 👑 Utenti Predefiniti

### Admin
- Email: `admin@crazy.com`
- Password: `amministratore123`

### VIP (accesso gratuito)
- `vip1@gmail.com` / `vip1-1234`
- `vip2@gmail.com` / `vip2-1234`
- `vip3@gmail.com` / `vip3-1234`
- `vip4@gmail.com` / `vip4-1234`
- `vip5@gmail.com` / `vip5-1234`

## 📚 API Endpoints

### Auth
- `POST /api/auth/register` - Registrazione
- `POST /api/auth/login` - Login
- `POST /api/auth/refresh` - Refresh token
- `GET /api/auth/me` - Info utente
- `POST /api/auth/password-reset-request` - Richiesta reset
- `POST /api/auth/password-reset-confirm` - Conferma reset

### Stripe
- `POST /api/stripe/create-checkout-session` - Crea checkout
- `POST /api/stripe/create-portal-session` - Portale gestione
- `GET /api/stripe/subscription-status` - Stato abbonamento
- `POST /api/stripe/webhook` - Webhook Stripe

### Brain Tool
- `GET /api/brain/access-status` - Verifica accesso
- `POST /api/brain/session/start` - Avvia sessione
- `POST /api/brain/session/end` - Termina sessione
- `POST /api/brain/spin` - Aggiungi spin
- `GET /api/brain/decision` - Ottieni decisione
- `GET /api/brain/signals` - Segnali attivi
- `GET /api/brain/brains` - Stato MiniBrains

### Admin
- `GET /api/admin/dashboard` - Dashboard stats
- `GET /api/admin/users` - Lista utenti
- `POST /api/admin/users/{uuid}/activate` - Attiva utente
- `POST /api/admin/users/{uuid}/deactivate` - Disattiva utente
- `POST /api/admin/users/{uuid}/make-vip` - Rendi VIP

## 🛡️ Sicurezza Implementata

1. **Password Hashing**: bcrypt con cost factor 12
2. **JWT Tokens**: Access token (30min) + Refresh token (7 giorni)
3. **Rate Limiting**: SlowAPI con limiti per endpoint
4. **CORS**: Configurato per produzione
5. **Security Headers**: HSTS, CSP, X-Frame-Options, etc.
6. **Input Validation**: Pydantic models
7. **SQL Injection Protection**: SQLAlchemy ORM
8. **XSS Protection**: Sanitizzazione input
9. **Audit Logging**: Tracciamento tutte le azioni
10. **Account Lockout**: Dopo troppi tentativi falliti

## 📄 Licenza

Proprietario - Tutti i diritti riservati
