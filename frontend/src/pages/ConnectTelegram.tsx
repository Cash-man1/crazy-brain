import { Link } from 'react-router-dom'

const BOT_USER = (import.meta.env.VITE_TELEGRAM_BOT_USERNAME as string | undefined)?.trim().replace(/^@/, '') || ''

export default function ConnectTelegram() {
  const botHref = BOT_USER ? `https://t.me/${BOT_USER}` : ''

  return (
    <div className="dashboard dashboard--live-full">
      <main className="dashboard-content dashboard-content--live">
        <div className="container container--live-full">
          <div className="welcome-section live-welcome-tight">
            <h1>Segnali su Telegram (solo bot)</h1>
            <p className="description" style={{ maxWidth: 720, lineHeight: 1.55 }}>
              Non serve account nell’app: il backend invia i messaggi al **bot Telegram** che hai creato con
              BotFather, verso la **tua chat** (il tuo <strong>chat id</strong> numerico).
            </p>
          </div>

          <div className="status-card" style={{ marginBottom: 14 }}>
            <h3 className="live-panel-title" style={{ marginBottom: 10 }}>
              1) Apri <code style={{ fontSize: '0.9em' }}>backend/.env</code> (o le variabili su Render)
            </h3>
            <p className="description" style={{ marginBottom: 10 }}>
              Imposta almeno queste righe (token e username li copi da BotFather):
            </p>
            <pre
              style={{
                background: 'rgba(0,0,0,0.35)',
                padding: 14,
                borderRadius: 8,
                overflow: 'auto',
                fontSize: '0.88rem',
                lineHeight: 1.45,
                border: '1px solid rgba(255,255,255,0.12)',
              }}
            >
              {`NOTIFY_SIGNALS_ENABLED=true
TELEGRAM_BOT_TOKEN=il_token_del_bot
TELEGRAM_BOT_USERNAME=nome_bot_senza_chiocciola
TELEGRAM_CHAT_IDS=IL_TUO_CHAT_ID
NOTIFY_MIN_CONFIDENCE=0.45

# Opzionale: solo certi segmenti verso TELEGRAM_CHAT_IDS (CSV, es. 1,2,CH)
# NOTIFY_BROADCAST_SEGMENTS=1,2,CH`}
            </pre>
            <p className="description" style={{ marginTop: 12 }}>
              Poi <strong>riavvia il backend</strong> (chiudi la finestra uvicorn e rilancia <code>avvio.bat</code> o il
              comando che usi).
            </p>
          </div>

          <div className="status-card" style={{ marginBottom: 14 }}>
            <h3 className="live-panel-title" style={{ marginBottom: 10 }}>
              2) Scopri il tuo chat id
            </h3>
            <p className="description">
              Su Telegram apri un bot come <strong>@userinfobot</strong> o <strong>@getidsbot</strong>, invia un
              messaggio: ti risponde con il numero da mettere in <code>TELEGRAM_CHAT_IDS</code>. Più chat: separa con
              virgola.
            </p>
          </div>

          <div className="status-card" style={{ marginBottom: 14 }}>
            <h3 className="live-panel-title" style={{ marginBottom: 10 }}>
              3) (Opzionale) Apri il bot
            </h3>
            <p className="description" style={{ marginBottom: 10 }}>
              Per ricevere messaggi il bot deve poter scriverti; aprirlo e premere <strong>START</strong> non basta da
              solo per salvare l’id nel server — l’id va nel <code>.env</code> come sopra.
            </p>
            {botHref ? (
              <a className="btn btn-primary" href={botHref} target="_blank" rel="noopener noreferrer">
                Apri @{BOT_USER} su Telegram
              </a>
            ) : (
              <p className="description">
                Per mostrare qui il pulsante “Apri bot”, aggiungi in <code>frontend/.env</code>:{' '}
                <code>VITE_TELEGRAM_BOT_USERNAME=nome_del_tuo_bot</code> (senza @) e riavvia Vite.
              </p>
            )}
          </div>

          <div className="status-card">
            <Link to="/dashboard" className="btn btn-secondary">
              Torna alla dashboard
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}
