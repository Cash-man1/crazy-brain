import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Brain } from 'lucide-react'
import LegalFooter from '../components/LegalFooter'
import InstagramMarkLink from '../components/InstagramMarkLink'
import { INSTAGRAM_URL } from '../config/social'
import { formatItalyFromBackendIso, formatItalyTableRowTime } from '../lib/formatTime'

const DEFAULT_HISTORY_CAP = 5000

/** Allineato alla colonna "Moltip." del sito: solo moltiplicatore finale (da backend). */
function displayFinalMultiplier(r: any): string {
  const fm = r?.final_multiplier
  if (fm != null && fm !== '') return `${fm}x`
  return '—'
}

const API_CANDIDATES = [
  import.meta.env.VITE_API_URL,
  'http://127.0.0.1:8000',
  'http://localhost:8000',
].filter(Boolean) as string[]

const segmentColor: Record<string, string> = {
  '1': '#00b3a4',
  '2': '#f3c64e',
  '5': '#ff5c63',
  '10': '#c879ff',
  CH: '#58d47f',
  CF: '#66b5ff',
  PA: '#d08bff',
  CT: '#ff4f4f'
}

const SEGMENT_ORDER = ['1', '2', '5', '10', 'CH', 'CF', 'PA', 'CT'] as const
const SEGMENT_LABEL: Record<string, string> = {
  '1': '1',
  '2': '2',
  '5': '5',
  '10': '10',
  CH: 'Cash Hunt',
  CF: 'Coin Flip',
  PA: 'Pachinko',
  CT: 'Crazy Time',
}

const instagramHref = INSTAGRAM_URL || 'https://www.instagram.com/'

export default function LiveDashboardNoAuth() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [loading, setLoading] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [statsWindowIdx, setStatsWindowIdx] = useState<number | null>(null)

  const load = async () => {
    if (loading) return
    setLoading(true)
    let lastError = 'Failed to fetch'
    for (const base of API_CANDIDATES) {
      try {
        const res = await fetch(`${base}/api/brain/auto-brain-public?_ts=${Date.now()}`, { cache: 'no-store' })
        const payload = await res.json()
        if (!res.ok) throw new Error(payload?.detail || 'Errore caricamento dati')
        setData(payload)
        setApiBase(base)
        setError('')
        setLoading(false)
        return
      } catch (e: any) {
        lastError = `${base}: ${e.message}`
      }
    }
    setError(lastError)
    setLoading(false)
  }

  useEffect(() => {
    load()
    const id = window.setInterval(load, 1000)
    return () => window.clearInterval(id)
  }, [])

  const hot = data?.hot_signals || []
  const phaseHeatRank = (phase: string) => {
    const p = String(phase || '').toLowerCase()
    if (p === 'confermato') return 3
    if (p === 'attacco') return 2
    return 1
  }
  const hotSorted = [...hot].sort((a: any, b: any) => {
    const ph = phaseHeatRank(b.phase) - phaseHeatRank(a.phase)
    if (ph !== 0) return ph
    const dc = (Number(b.confidence) || 0) - (Number(a.confidence) || 0)
    if (Math.abs(dc) > 1e-9) return dc
    return (Number(b.ev) || -1e9) - (Number(a.ev) || -1e9)
  })
  const brains = data?.mini_brains ? Object.values(data.mini_brains) : []
  const pollSec = data?.poll_interval_seconds ?? 1
  const pred = data?.prediction_accuracy || {}
  const acc = pred.by_segment || {}
  const accSelective = pred.by_segment_selective || {}
  const primaryMode = pred.primary_mode as string | undefined
  const toMinutes = (t: string) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(t || '')
    if (!m) return -1
    return Number(m[1]) * 60 + Number(m[2])
  }
  const latestRowsAll = [...(data?.latest_rows || [])].sort(
    (a: any, b: any) => toMinutes(String(b?.time || '')) - toMinutes(String(a?.time || ''))
  )
  const latestRowsCompact = latestRowsAll.slice(0, 22)

  const liveStats = data?.live_statistics
  const statWindows = (liveStats?.windows || []) as any[]
  const statIdx =
    statsWindowIdx != null && statsWindowIdx < statWindows.length ? statsWindowIdx : Math.max(0, statWindows.length - 1)
  const statWin = statWindows[statIdx]

  const labelForIcon = (icon: string) => {
    const t = String(icon || '').toLowerCase()
    if (t.includes('pachinko')) return 'PA'
    if (t.includes('coin')) return 'CF'
    if (t.includes('cash')) return 'CH'
    if (t.includes('crazy')) return 'CT'
    if (['1', '2', '5', '10'].includes(String(icon))) return String(icon)
    return icon || ''
  }
  const wheelSegForRow = (r: any) => {
    // Priorita': segmento ruota gia normalizzato dal backend.
    const direct = String(r?.wheel_segment || r?.segment || '').trim()
    if (SEGMENT_ORDER.includes(direct as any)) return direct
    const fromResult = labelForIcon(String(r?.wheel_result || ''))
    if (SEGMENT_ORDER.includes(fromResult as any)) return fromResult
    const fromIcon = labelForIcon(String(r?.wheel_icon || ''))
    if (SEGMENT_ORDER.includes(fromIcon as any)) return fromIcon
    return ''
  }

  return (
    <div className="dashboard dashboard--live-full">
      <main className="dashboard-content dashboard-content--live">
        <div className="container container--live-full">
          <div className="welcome-section live-welcome-tight">
            <h1 className="live-brand-title">
              <Brain className="live-brand-icon" aria-hidden strokeWidth={1.75} />
              <span>CRAZY-BRAIN</span>
            </h1>
          </div>

          {error && <div className="error-message">{error}</div>}

          {data && (
            <div className="status-grid" style={{ marginBottom: 18 }}>
              <div className="status-card">
                <button
                  type="button"
                  onClick={() => setSourceOpen(true)}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255,255,255,0.25)',
                    color: 'inherit',
                    padding: '6px 12px',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: '1rem',
                  }}
                >
                  Fonte
                </button>
                <div style={{ marginTop: 10, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Link className="btn btn-primary" to="/connect">
                    Segnali su Telegram (config bot)
                  </Link>
                  <InstagramMarkLink
                    href={instagramHref}
                    title={
                      INSTAGRAM_URL
                        ? 'Profilo Instagram'
                        : 'Instagram — imposta VITE_INSTAGRAM_URL su Render per il tuo profilo'
                    }
                    className="btn btn-secondary"
                  />
                  <div className="description" style={{ marginLeft: 4 }}>
                    I segnali via Telegram: vedi <strong>/connect</strong> — solo variabili sul backend, nessun login
                    nell’app.
                  </div>
                </div>
              </div>
            </div>
          )}

          {sourceOpen && data && (
            <div
              role="dialog"
              aria-modal="true"
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.65)',
                zIndex: 1000,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 16,
              }}
              onClick={() => setSourceOpen(false)}
            >
              <div
                className="status-card"
                style={{ maxWidth: 520, width: '100%', maxHeight: '85vh', overflow: 'auto' }}
                onClick={(e) => e.stopPropagation()}
              >
                <h3 style={{ marginTop: 0 }}>Dettaglio fonte</h3>
                <div className="description">{data.source_url}</div>
                <div className="description">backend: {apiBase || '--'}</div>
                <div className="description">source_ok: {String(data.source_ok)}</div>
                <div className="description">righe lette: {data.scraper_rows_count ?? '--'}</div>
                <div className="description">tracked_rows: {data.tracked_rows ?? 0}</div>
                <div className="description">ultima ora sorgente: {data.source_latest_time ?? '--'}</div>
                <div className="description">ritardo sorgente: {data.source_lag_seconds != null ? `${Math.round(data.source_lag_seconds)}s` : '--'}</div>
                <div className="description">
                  Ultimo poll (Italia): {formatItalyFromBackendIso(data.last_poll)}
                </div>
                <div className="description" style={{ opacity: 0.85, fontSize: '0.85rem' }}>
                  UTC tecnico: {data.last_poll || '--'}
                </div>
                <div className="description">errore: {data.source_error || 'nessuno'}</div>
                <button
                  type="button"
                  onClick={() => setSourceOpen(false)}
                  style={{ marginTop: 12, padding: '8px 16px', cursor: 'pointer' }}
                >
                  Chiudi
                </button>
              </div>
            </div>
          )}

          {liveStats && statWindows.length > 0 && statWin && (
            <div className="live-panel live-stats-panel" style={{ marginBottom: 14 }}>
              <div className="live-stats-panel-head">
                <h3 className="live-panel-title" style={{ marginBottom: 0 }}>
                  Uscite sulla ruota vs media del gioco
                </h3>
                <select
                  className="live-stats-select"
                  value={statIdx}
                  onChange={(e) => setStatsWindowIdx(Number(e.target.value))}
                  aria-label="Quante uscite considerare"
                >
                  {statWindows.map((w: any, i: number) => (
                    <option key={i} value={i}>
                      {w.label}
                    </option>
                  ))}
                </select>
              </div>
              <p className="live-panel-hint" style={{ marginTop: 6 }}>
                {liveStats.note} In questo riquadro usiamo <strong>{liveStats.buffer_valid_spins}</strong> uscite con esito
                ruota chiaro. Il cervello ne ha già elaborate <strong>{liveStats.brain_spins_recorded ?? '—'}</strong>; su
                disco ne sono salvate fino a <strong>{liveStats.persisted_file_rows ?? '—'}</strong> (cronologia). I{' '}
                <strong>pattern</strong> utili restano in <code>public_patterns.json</code> e si ricaricano al riavvio; i
                pattern non più significativi vengono scartati automaticamente dal motore.
              </p>
              <div className="live-stats-kpis">
                <span title="Percentuale di giri in cui la Top Slot ha indicato la stessa casella che è uscita sulla ruota">
                  Top slot uguale alla ruota:{' '}
                  <strong>
                    {statWin.slot_wheel_match?.compared
                      ? `${(statWin.slot_wheel_match.rate * 100).toFixed(1)}% (${statWin.slot_wheel_match.matched} su ${statWin.slot_wheel_match.compared})`
                      : '—'}
                  </strong>
                </span>
                <span title="Numero riassuntivo: più è alto, più il quadro delle uscite è lontano da quello 'perfettamente equilibrato'">
                  Quanto il quadro è lontano dalla media ideale: <strong>{statWin.chi_square_vs_theory ?? '—'}</strong>
                </span>
                <span title="Moltiplicatore più alto visto nelle giocate selezionate">
                  Moltiplicatore più alto (in queste giocate): <strong>{statWin.max_multiplier_in_window ?? '—'}</strong>
                </span>
              </div>
              <div className="admin-users-table live-stats-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th title="Casella sulla ruota Crazy Time">Casella</th>
                      <th title="Quante volte è uscita in questo gruppo di giocate">Quante volte</th>
                      <th title="Quante volte ci si aspetterebbe in media, se tutto fosse perfettamente equilibrato">
                        Di solito (media)
                      </th>
                      <th title="1,0 = come la media; sotto 1 = uscita poco; sopra 1 = uscita spesso">
                        Rispetto alla media
                      </th>
                      <th title="0 = nella norma; valori grandi (positivi o negativi) = più insolito">
                        Quanto è insolito
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {SEGMENT_ORDER.map((seg) => {
                      const row = statWin.per_segment?.[seg] || {}
                      return (
                        <tr key={`st-${seg}`}>
                          <td>
                            <span className="mini-badge" style={{ background: segmentColor[seg] || '#333' }}>
                              {seg}
                            </span>
                          </td>
                          <td>{row.count ?? 0}</td>
                          <td>{row.expected ?? '—'}</td>
                          <td>{row.ratio_vs_expected != null ? row.ratio_vs_expected : '—'}</td>
                          <td>{row.z_vs_expected != null ? row.z_vs_expected : '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="live-stats-legend">
                <strong>Come leggere la tabella:</strong> «Di solito (media)» è quante volte uscirebbe quella casella se il
                gioco fosse perfettamente fedele alle probabilità ufficiali. «Rispetto alla media»: 1 è normale; più basso =
                uscita rara in questo gruppo; più alto = uscita frequente. «Quanto è insolito» è un indice tecnico: vicino
                a 0 è nella norma; valori molto alti (in valore assoluto) segnalano un caso più raro.
              </p>
            </div>
          )}

          <div className="live-public-layout">
            <div className="live-top-row">
              <div className="live-panel live-mini-panel">
                <h3 className="live-panel-title">Mini Brains</h3>
                <p className="live-panel-hint">
                  Conf conservativa con pochi dati. Campioni range e calibrazione vs caso.
                </p>
                <div className="mini-brains-grid live-mini-brains-grid">
                  {SEGMENT_ORDER.map((segKey) => {
                    const b = (brains as any[]).find((x: any) => x.segment === segKey)
                    if (!b) return null
                    const cal = b.calibration_vs_null || {}
                    const ci = b.attack_success_ci95 as number[] | null | undefined
                    const ciStr =
                      ci && ci.length === 2 ? `${(ci[0] * 100).toFixed(0)}–${(ci[1] * 100).toFixed(0)}%` : '—'
                    return (
                      <div className="mini-brain-card" key={b.segment}>
                        <div className="mini-top">
                          <span className="mini-badge" style={{ background: segmentColor[b.segment] || '#333' }}>{b.segment}</span>
                          <span className="mini-phase">{String(b.phase).toUpperCase()}</span>
                          <span className={`mini-ev ${b.ev >= 0 ? 'pos' : 'neg'}`}>EV: {b.ev}</span>
                        </div>
                        <div className="mini-line">Battery {Math.round((b.battery || 0))}%</div>
                        <div className="mini-line">Gap {b.gap_current}/{Math.round(b.expected_gap || 0)} — Conf {(b.confidence * 100).toFixed(1)}%</div>
                        {typeof b.confidence_raw === 'number' && (
                          <div className="mini-line" style={{ opacity: 0.85 }}>Conf grezza {(b.confidence_raw * 100).toFixed(1)}%</div>
                        )}
                        <div className="mini-line">Heat {b.heat} — Z {b.z_score} — Range {b.range}</div>
                        <div className="mini-line">
                          Attacchi: {b.attack_attempts ?? 0} ok {b.attack_successes ?? 0}
                          {b.attack_data_sparse ? ' (pochi dati)' : ''} — CI95 {ciStr}
                        </div>
                        <div className="mini-line">
                          Campioni range: {b.range_samples_n ?? 0}
                          {b.learned_last_update ? ` — ${String(b.learned_last_update).slice(11, 19)}` : ''}
                        </div>
                        <div className="mini-line" style={{ opacity: 0.9 }}>
                          vs caso: {cal.label ?? '—'} (z {cal.z_score_vs_null ?? '—'}
                          {cal.mc_p_ge_observed != null ? `, p≥ ${cal.mc_p_ge_observed}` : ''})
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="live-panel">
                <h3 className="live-panel-title">Ultimi esiti</h3>
                <p className="live-auto-mode-meta">
                  Auto mode attivo — {pollSec === 1 ? 'aggiornamento ogni secondo' : `aggiornamento ogni ${pollSec} secondi`}. Storico su disco: finestra scorrevole delle ultime{' '}
                  <strong>{data?.public_history_max_items ?? DEFAULT_HISTORY_CAP}</strong> giocate (5001, 5002… si
                  aggiungono; le più vecchie oltre il limite si eliminano in automatico). Ora salvate:{' '}
                  <strong>{data?.history_saved_rows ?? data?.history_saved_6h_rows ?? '—'}</strong> righe (persistenza
                  locale; al riavvio si ricarica quel file). Con Playwright la pagina casino viene filtrata
                  sul lasso <strong>{data?.scraper_cronologia_hours_hint ?? 6} h</strong> (variabile{' '}
                  <code>SCRAPER_CRONOLOGIA_HOURS</code> sul backend/worker).
                </p>
                <p className="live-panel-hint">
                  {latestRowsAll.length === 0
                    ? 'Nessuna riga in buffer.'
                    : `Ultime ${latestRowsCompact.length} di ${latestRowsAll.length} in elenco — scroll per vedere tutte nella finestra.`}
                </p>
                <div className="live-outcomes-scroll admin-users-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Ora</th>
                        <th>Slot</th>
                        <th>Esito</th>
                        <th>Moltip.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {latestRowsCompact.length === 0 && (
                        <tr>
                          <td colSpan={4}>Nessun esito letto ancora</td>
                        </tr>
                      )}
                      {latestRowsCompact.map((r: any, idx: number) => {
                        const wheelSeg = wheelSegForRow(r)
                        return (
                          <tr key={`${r.time}-${r.segment}-${idx}`}>
                            <td title={r.settled_at_utc ? formatItalyFromBackendIso(r.settled_at_utc) : undefined}>
                              {formatItalyTableRowTime(r)}
                            </td>
                            <td>
                              {r.slot_icon ? (
                                <span
                                  className="mini-badge"
                                  style={{ background: segmentColor[labelForIcon(r.slot_icon)] || '#333', marginRight: 6 }}
                                >
                                  {labelForIcon(r.slot_icon)}
                                </span>
                              ) : null}
                              <span style={{ fontSize: '0.8rem' }}>{r.slot_result || '-'}</span>
                            </td>
                            <td>
                              {wheelSeg ? (
                                <span className="mini-badge" style={{ background: segmentColor[wheelSeg] || '#333' }}>
                                  {wheelSeg}
                                </span>
                              ) : (
                                '-'
                              )}
                            </td>
                            <td>{displayFinalMultiplier(r)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="live-hot-hero">
              <div className="live-hot-hero-head">
                <h3>Segnali caldi</h3>
                {hotSorted.length > 0 && hotSorted[0]?.segment && (
                  <span className="live-hot-pill">Più caldo: {hotSorted[0].segment}</span>
                )}
              </div>
              {hotSorted.length > 0 && (
                <p className="live-hot-sort-hint">Ordine: dal più caldo in alto — confermato prima di attacco, poi confidence e EV.</p>
              )}
              {hotSorted.length === 0 ? (
                <p className="live-hot-empty">Nessun segnale in attacco / confermato al momento — il cervello non propone giocate “calde” su questo giro.</p>
              ) : (
                <div className="live-hot-cards live-hot-cards--column">
                  {hotSorted.map((s: any, idx: number) => (
                    <div
                      key={`${s.segment}-${idx}`}
                      className="live-hot-card"
                      style={{ borderColor: segmentColor[s.segment] || 'rgba(255,255,255,0.15)' }}
                    >
                      <div className="live-hot-card-top">
                        <span className="live-hot-rank" aria-hidden>
                          {idx + 1}
                        </span>
                        <span className="live-hot-seg" style={{ background: segmentColor[s.segment] || '#444' }}>
                          {s.segment}
                        </span>
                        <span style={{ color: '#b8bfd7', fontWeight: 600, fontSize: '0.9rem' }}>{s.phase}</span>
                      </div>
                      <div className="live-hot-meta">
                        <span>Confidence</span>
                        <strong>{(s.confidence * 100).toFixed(1)}%</strong>
                        <span>EV</span>
                        <strong>{s.ev}</strong>
                        <span>Range</span>
                        <strong>{s.range_remaining}</strong>
                        <span>Battery</span>
                        <strong>{Math.round(s.battery ?? 0)}%</strong>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="live-predictions-grid">
              <div>
                <h3 className="section-title">Previsione → esito (continua)</h3>
                <p style={{ opacity: 0.85, fontSize: '0.82rem', marginBottom: 8 }}>
                  Ogni giro un segmento top (EV max). Tentativi ≈ giri.
                </p>
                <div className="status-card admin-users-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Segmento</th>
                        <th>Tent.</th>
                        <th>Ok</th>
                        <th>%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {SEGMENT_ORDER.map((seg) => {
                        const row = acc[seg] || { attempts: 0, hits: 0, rate: null }
                        const pct = row.rate != null ? `${(row.rate * 100).toFixed(1)}%` : '—'
                        return (
                          <tr key={seg}>
                            <td>
                              <span className="mini-badge" style={{ background: segmentColor[seg] || '#333', marginRight: 8 }}>
                                {seg}
                              </span>
                              {SEGMENT_LABEL[seg] || seg}
                            </td>
                            <td>{row.attempts ?? 0}</td>
                            <td>{row.hits ?? 0}</td>
                            <td>{pct}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <div className="description" style={{ marginTop: 8, fontSize: '0.82rem' }}>
                    Giri sessione: {pred.spin_count ?? data?.session?.spin_count ?? '—'}
                    {primaryMode === 'continuous' && <> — Σ tent. ≈ giri.</>}
                  </div>
                </div>
              </div>
              <div>
                <h3 className="section-title">Previsione selettiva (hot / meta)</h3>
                <p style={{ opacity: 0.8, fontSize: '0.82rem', marginBottom: 8 }}>
                  Solo con segnale caldo o meta PLAY.
                </p>
                <div className="status-card admin-users-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Segmento</th>
                        <th>Tent.</th>
                        <th>Ok</th>
                        <th>%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {SEGMENT_ORDER.map((seg) => {
                        const row = accSelective[seg] || { attempts: 0, hits: 0, rate: null }
                        const pct = row.rate != null ? `${(row.rate * 100).toFixed(1)}%` : '—'
                        return (
                          <tr key={`sel-${seg}`}>
                            <td>
                              <span className="mini-badge" style={{ background: segmentColor[seg] || '#333', marginRight: 8 }}>
                                {seg}
                              </span>
                              {SEGMENT_LABEL[seg] || seg}
                            </td>
                            <td>{row.attempts ?? 0}</td>
                            <td>{row.hits ?? 0}</td>
                            <td>{pct}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
        <LegalFooter variant="dashboard" />
      </main>
    </div>
  )
}
