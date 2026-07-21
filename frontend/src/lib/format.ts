/** Formateo de duraciones y fechas para la interfaz, en español. */

export function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds < 0) return '—'
  if (seconds < 60) return 'hace un momento'

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min`

  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  if (hours < 24) return restMinutes ? `${hours} h ${restMinutes} min` : `${hours} h`

  const days = Math.floor(hours / 24)
  const restHours = hours % 24
  return restHours ? `${days} d ${restHours} h` : `${days} d`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const date = parseUtc(iso)
  return date.toLocaleString('es', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRelative(iso: string | null): string {
  if (!iso) return '—'
  const seconds = (Date.now() - parseUtc(iso).getTime()) / 1000
  if (seconds < 60) return 'hace segundos'
  return `hace ${formatUptime(seconds)}`
}

/**
 * El backend serializa fechas UTC sin sufijo de zona. Sin la `Z`, el navegador
 * las interpretaría como hora local y los tiempos saldrían desplazados.
 */
function parseUtc(iso: string): Date {
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`
  return new Date(normalized)
}

export function confidenceLabel(confidence: number): string {
  if (confidence >= 0.85) return 'alta'
  if (confidence >= 0.6) return 'media'
  if (confidence > 0) return 'baja'
  return 'sin datos'
}
