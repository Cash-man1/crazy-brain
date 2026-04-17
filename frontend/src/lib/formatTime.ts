/** Backend invia ISO UTC con suffisso Z; mostra ora locale Italia. */
export function formatItalyFromBackendIso(iso: string | undefined | null): string {
  if (!iso) return '--'
  const s = String(iso).trim()
  const hasTz = /Z$|[+-]\d{2}:\d{2}$/.test(s)
  const normalized = hasTz ? s : `${s}Z`
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString('it-IT', {
    timeZone: 'Europe/Rome',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Tabella ultimi esiti: data/ora in Italia (stesso fuso della pagina casino). */
export function formatItalyShortFromIso(iso: string | undefined | null): string {
  if (!iso) return ''
  const s = String(iso).trim()
  const hasTz = /Z$|[+-]\d{2}:\d{2}$/.test(s)
  const normalized = hasTz ? s : `${s}Z`
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('it-IT', {
    timeZone: 'Europe/Rome',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** `datetime_text` senza fuso dall'API Evolution (UTC wall clock). */
function looksLikeIsoUtcDateTime(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(s.trim())
}

/** Testo riga tabella casino.org da Playwright (es. "17 Apr 18:27"). */
function looksLikeScraperCasinoDateTime(s: string): boolean {
  return /^\d{1,2}\s+[A-Za-zÀ-ÿ]{3,}\b/.test(s.trim())
}

/**
 * Colonna ora tabella: allinea al sito (Europe/Rome).
 * - Evolution: usa `settled_at_utc` o `datetime_text` ISO (entrambi UTC → Italia).
 * - Playwright: testo umano della riga se presente, altrimenti `time`.
 */
export function formatItalyTableRowTime(row: {
  settled_at_utc?: string | null
  datetime_text?: string | null
  time?: string | null
}): string {
  const iso = row.settled_at_utc
  if (iso) {
    const s = formatItalyShortFromIso(iso)
    if (s) return s
  }
  const dt = String(row.datetime_text || '').trim()
  if (dt && looksLikeIsoUtcDateTime(dt)) {
    const normalized = dt.includes('T') ? dt : dt.replace(' ', 'T')
    const s = formatItalyShortFromIso(normalized)
    if (s) return s
  }
  if (dt && looksLikeScraperCasinoDateTime(dt)) return dt
  const t = String(row.time || '').trim()
  return t || '—'
}
