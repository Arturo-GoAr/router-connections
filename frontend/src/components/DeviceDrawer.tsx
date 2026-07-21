import { Star, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { CategoryOption, DeviceCategory, DeviceDetail, Tag } from '../api/types'
import { categoryStyle } from '../lib/categories'
import { confidenceLabel, formatDateTime, formatUptime } from '../lib/format'
import { Button, Chip, ErrorNote, Field, Input, Select, Spinner, TextArea } from './ui'

interface Props {
  deviceId: number
  categories: CategoryOption[]
  tags: Tag[]
  onClose: () => void
  onChanged: () => void
}

export function DeviceDrawer({ deviceId, categories, tags, onClose, onChanged }: Props) {
  const [device, setDevice] = useState<DeviceDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)

  const [alias, setAlias] = useState('')
  const [notes, setNotes] = useState('')
  const [category, setCategory] = useState<string>('')

  useEffect(() => {
    let active = true
    setDevice(null)
    setError(null)

    api
      .getDevice(deviceId)
      .then((detail) => {
        if (!active) return
        setDevice(detail)
        setAlias(detail.alias ?? '')
        setNotes(detail.notes ?? '')
        setCategory(detail.category_override ?? '')
      })
      .catch((err: Error) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [deviceId])

  // Cerrar con Escape es lo que espera cualquiera de un panel lateral.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateDevice(deviceId, {
        alias: alias.trim() || null,
        notes: notes.trim() || null,
        category_override: category ? (category as DeviceCategory) : null,
        clear_category_override: !category,
      })
      setDevice(updated)
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const runPortScan = async (profile: string) => {
    setScanning(true)
    setError(null)
    try {
      await api.scanPorts(deviceId, profile)
      setDevice(await api.getDevice(deviceId))
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setScanning(false)
    }
  }

  const toggleTag = async (tag: Tag) => {
    if (!device) return
    const attached = device.tags.some((item) => item.id === tag.id)
    try {
      const updated = attached
        ? await api.detachTag(deviceId, tag.id)
        : await api.attachTag(deviceId, tag.id)
      setDevice(updated)
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const toggleFavorite = async () => {
    if (!device) return
    try {
      setDevice(await api.updateDevice(deviceId, { is_favorite: !device.is_favorite }))
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const forget = async () => {
    if (!window.confirm('¿Olvidar este dispositivo y todo su historial? Si sigue en la red, el próximo barrido volverá a descubrirlo sin alias ni etiquetas.')) {
      return
    }
    try {
      await api.deleteDevice(deviceId)
      onChanged()
      onClose()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const openPorts = device?.ports.filter((port) => port.state === 'open') ?? []
  const style = device ? categoryStyle(device.category) : null

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      <aside className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto border-l border-edge bg-panel shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-edge bg-panel/95 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            <p className="flex items-center gap-2 truncate text-base font-semibold text-slate-100">
              {style && <style.icon className="h-4 w-4 shrink-0 text-slate-300" strokeWidth={1.5} />}
              {device?.display_name ?? 'Cargando…'}
            </p>
            {device && (
              <p className="truncate font-mono text-xs text-slate-400">
                {device.ip} · {device.mac}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-400 transition-colors hover:bg-panel-soft hover:text-slate-100"
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </header>

        {!device && !error && (
          <div className="flex items-center gap-2 p-6 text-sm text-slate-400">
            <Spinner /> Cargando dispositivo…
          </div>
        )}

        {error && (
          <div className="p-5">
            <ErrorNote message={error} />
          </div>
        )}

        {device && (
          <div className="space-y-6 p-5">
            {/* --- Estado --- */}
            <section className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-slate-500">Estado</p>
                <p className={device.is_online ? 'text-emerald-300' : 'text-slate-400'}>
                  {device.is_online ? 'En línea' : 'Desconectado'}
                </p>
              </div>
              <div>
                <p className="text-slate-500">Conectado desde hace</p>
                <p className="text-slate-200">{formatUptime(device.uptime_seconds)}</p>
              </div>
              <div>
                <p className="text-slate-500">Primera vez visto</p>
                <p className="text-slate-200">{formatDateTime(device.first_seen)}</p>
              </div>
              <div>
                <p className="text-slate-500">Última vez visto</p>
                <p className="text-slate-200">{formatDateTime(device.last_seen)}</p>
              </div>
              <div className="col-span-2">
                <p className="text-slate-500">Fabricante (según la MAC)</p>
                <p className="text-slate-200">{device.vendor ?? 'desconocido o MAC aleatoria'}</p>
              </div>
            </section>

            {/* --- Cómo se clasificó --- */}
            <section className="rounded-xl border border-edge/70 bg-panel-soft/40 p-3">
              <div className="flex items-center gap-2">
                <Chip className={style!.chip}>{style!.label}</Chip>
                <span className="text-[11px] text-slate-500">
                  confianza {confidenceLabel(device.detection_confidence)}
                  {device.category_override && ' · fijada por ti'}
                </span>
              </div>
              {device.detection_reason && (
                <p className="mt-2 text-xs leading-relaxed text-slate-400">
                  <span className="text-slate-500">Por qué: </span>
                  {device.detection_reason}
                </p>
              )}
            </section>

            {/* --- Edición --- */}
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Personalizar
              </h3>
              <Field label="Nombre" hint="Sustituye al nombre detectado automáticamente.">
                <Input
                  value={alias}
                  onChange={(event) => setAlias(event.target.value)}
                  placeholder={device.hostname ?? 'Ej. TV de la sala'}
                />
              </Field>
              <Field label="Categoría" hint="Déjalo en automático para usar la detección.">
                <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">
                    Automático ({categoryStyle(device.detected_category).label})
                  </option>
                  {categories.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Notas">
                <TextArea
                  rows={2}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Cualquier cosa que quieras recordar de este dispositivo"
                />
              </Field>

              <div className="flex flex-wrap gap-2">
                <Button variant="primary" onClick={save} loading={saving}>
                  Guardar cambios
                </Button>
                <Button onClick={toggleFavorite}>
                  <Star
                    className={`h-3.5 w-3.5 ${device.is_favorite ? 'fill-amber-300 text-amber-300' : ''}`}
                  />
                  {device.is_favorite ? 'Quitar de favoritos' : 'Marcar favorito'}
                </Button>
              </div>
            </section>

            {/* --- Etiquetas --- */}
            {tags.length > 0 && (
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Etiquetas
                </h3>
                <div className="flex flex-wrap gap-2">
                  {tags.map((tag) => {
                    const active = device.tags.some((item) => item.id === tag.id)
                    return (
                      <button
                        key={tag.id}
                        onClick={() => toggleTag(tag)}
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 transition-opacity ${
                          active ? 'ring-transparent' : 'opacity-50 ring-edge hover:opacity-90'
                        }`}
                        style={
                          active
                            ? { backgroundColor: `${tag.color}22`, color: tag.color }
                            : undefined
                        }
                      >
                        {tag.name}
                      </button>
                    )
                  })}
                </div>
              </section>
            )}

            {/* --- Puertos --- */}
            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Puertos abiertos
                </h3>
                <div className="flex gap-2">
                  <Button onClick={() => runPortScan('quick')} loading={scanning}>
                    Rápido
                  </Button>
                  <Button onClick={() => runPortScan('common')} loading={scanning}>
                    Completo
                  </Button>
                </div>
              </div>

              {device.last_port_scan === null ? (
                <p className="text-xs text-slate-500">
                  Todavía no se han escaneado los puertos de este dispositivo.
                </p>
              ) : openPorts.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No se encontró ningún puerto abierto en el último escaneo.
                </p>
              ) : (
                <ul className="divide-y divide-edge/60 overflow-hidden rounded-xl border border-edge/70">
                  {openPorts.map((port) => (
                    <li key={port.id} className="flex items-start gap-3 px-3 py-2">
                      <span className="font-mono text-sm text-sky-300">{port.port}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-slate-200">{port.service ?? 'servicio desconocido'}</p>
                        {port.banner && (
                          <p className="truncate font-mono text-[11px] text-slate-500" title={port.banner}>
                            {port.banner}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* --- Historial --- */}
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Historial de conexión
              </h3>
              {device.recent_sessions.length === 0 ? (
                <p className="text-xs text-slate-500">Sin sesiones registradas todavía.</p>
              ) : (
                <ul className="space-y-1">
                  {device.recent_sessions.slice(0, 8).map((session) => (
                    <li
                      key={session.id}
                      className="flex items-center justify-between rounded-lg bg-panel-soft/40 px-3 py-1.5 text-xs"
                    >
                      <span className="text-slate-300">{formatDateTime(session.started_at)}</span>
                      <span className="text-slate-500">
                        {session.ended_at ? formatUptime(session.duration_seconds) : 'en curso'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="border-t border-edge/60 pt-4">
              <Button variant="danger" onClick={forget}>
                Olvidar dispositivo
              </Button>
            </section>
          </div>
        )}
      </aside>
    </div>
  )
}
