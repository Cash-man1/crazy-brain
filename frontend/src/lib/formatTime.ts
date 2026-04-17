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
