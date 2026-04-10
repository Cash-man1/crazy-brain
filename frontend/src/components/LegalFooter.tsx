type Props = {
  /** 'auth' = card sotto form; 'dashboard' = più compatto in fondo pagina */
  variant?: 'auth' | 'dashboard'
}

export default function LegalFooter({ variant = 'auth' }: Props) {
  const isDash = variant === 'dashboard'
  return (
    <div className={isDash ? 'legal-footer legal-footer--dashboard' : 'auth-footer'}>
      {!isDash && <span className="brand">Crazy Brain</span>}
      <div className={`disclaimer legal-disclaimer ${isDash ? 'legal-disclaimer--compact' : ''}`}>
        <p>
          <strong>Avviso legale e gioco responsabile.</strong> Crazy Brain è uno strumento di analisi e intrattenimento: non
          costituisce consiglio finanziario, non garantisce vincite e non invita a giocare. Il gioco d’azzardo può causare
          dipendenza e perdite economiche. <strong>18+</strong>. Gioca solo se è legale nel tuo Paese e imposta limiti di
          tempo e budget.
        </p>
        <p>
          <strong>Italia — aiuto dipendenza:</strong>{' '}
          <a href="tel:800558822">800 558 822</a> (numero verde ADM, gratuito){' '}
          —{' '}
          <a href="https://www.giocatorisullorlo.it" target="_blank" rel="noopener noreferrer">
            giocatorisullorlo.it
          </a>
          . Per informazioni sul gioco lecito:{' '}
          <a href="https://www.adm.gov.it" target="_blank" rel="noopener noreferrer">
            adm.gov.it
          </a>
          .
        </p>
        <p>
          Registrandoti o usando il servizio accetti i termini applicabili; eventuali abbonamenti sono soggetti alle
          condizioni contrattuali comunicate al momento dell’acquisto.
        </p>
      </div>
    </div>
  )
}
