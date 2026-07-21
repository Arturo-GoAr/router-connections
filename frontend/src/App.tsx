import { Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from './api/client'
import type { CategoryOption, Device, NetworkStatus, Tag } from './api/types'
import { DeviceCard } from './components/DeviceCard'
import { DeviceDrawer } from './components/DeviceDrawer'
import { Diagnostics } from './components/Diagnostics'
import { NetworkPanel } from './components/NetworkPanel'
import { PortsPanel } from './components/PortsPanel'
import { TagManager } from './components/TagManager'
import { Button, EmptyState, ErrorNote, Input, Panel, Select, Spinner } from './components/ui'
import { useLiveEvents } from './hooks/useLiveEvents'

export default function App() {
  const [network, setNetwork] = useState<NetworkStatus | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [categories, setCategories] = useState<CategoryOption[]>([])
  const [tags, setTags] = useState<Tag[]>([])

  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [query, setQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [onlineOnly, setOnlineOnly] = useState(false)

  const refreshDevices = useCallback(async () => {
    try {
      setDevices(await api.listDevices())
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  const refreshNetwork = useCallback(async () => {
    try {
      setNetwork(await api.getNetwork())
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  const refreshTags = useCallback(async () => {
    try {
      setTags(await api.listTags())
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    void (async () => {
      setLoading(true)
      await Promise.all([refreshDevices(), refreshNetwork(), refreshTags()])
      try {
        setCategories(await api.categories())
      } catch {
        /* el selector puede vivir sin la lista; no vale la pena molestar al usuario */
      }
      setLoading(false)
    })()
  }, [refreshDevices, refreshNetwork, refreshTags])

  // El backend avisa por WebSocket cuando termina un barrido o cambia algo,
  // así que la interfaz no necesita hacer polling.
  const { connected } = useLiveEvents(
    useCallback(
      (event) => {
        if (event.type === 'scan:started') setScanning(true)
        if (event.type === 'scan:finished') {
          setScanning(false)
          void refreshDevices()
          void refreshNetwork()
        }
        if (event.type === 'devices:updated' || event.type === 'device:updated') {
          void refreshDevices()
        }
      },
      [refreshDevices, refreshNetwork],
    ),
  )

  const runScan = async (withPorts: boolean) => {
    setScanning(true)
    setError(null)
    try {
      await api.scan(withPorts, 'quick')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setScanning(false)
      await Promise.all([refreshDevices(), refreshNetwork()])
    }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return devices.filter((device) => {
      if (onlineOnly && !device.is_online) return false
      if (categoryFilter && device.category !== categoryFilter) return false
      if (!needle) return true
      return [device.display_name, device.ip, device.mac, device.vendor, device.hostname]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(needle))
    })
  }, [devices, query, categoryFilter, onlineOnly])

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-50">Router Connections</h1>
          <p className="mt-0.5 text-xs text-slate-400">Inventario y monitoreo de tu red local</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span
            className="flex items-center gap-1.5 text-[11px] text-slate-500"
            title={connected ? 'Conectado al servidor' : 'Sin conexión con el servidor'}
          >
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-rose-400'}`} />
            {connected ? 'en vivo' : 'desconectado'}
          </span>
          <Button onClick={() => runScan(false)} loading={scanning}>
            Buscar dispositivos
          </Button>
          <Button variant="primary" onClick={() => runScan(true)} loading={scanning}>
            Buscar + escanear puertos
          </Button>
        </div>
      </header>

      {error && <ErrorNote message={error} />}
      {network && <Diagnostics items={network.diagnostics} />}

      <NetworkPanel status={network} />

      <Panel
        title="Dispositivos"
        subtitle={`${filtered.length} de ${devices.length} mostrados`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar por nombre, IP, MAC…"
              className="w-52"
            />
            <Select
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
              className="w-40"
            >
              <option value="">Todas las categorías</option>
              {categories.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={onlineOnly}
                onChange={(event) => setOnlineOnly(event.target.checked)}
                className="accent-sky-500"
              />
              Solo en línea
            </label>
          </div>
        }
      >
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner /> Cargando dispositivos…
          </p>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Search}
            title={devices.length === 0 ? 'Todavía no hay dispositivos' : 'Ningún dispositivo coincide'}
            detail={
              devices.length === 0
                ? 'Pulsa "Buscar dispositivos" para barrer tu red. El primer barrido tarda unos segundos.'
                : 'Prueba a limpiar el buscador o los filtros.'
            }
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
            {filtered.map((device) => (
              <DeviceCard
                key={device.id}
                device={device}
                selected={device.id === selectedId}
                onSelect={(selected) => setSelectedId(selected.id)}
              />
            ))}
          </div>
        )}
      </Panel>

      <PortsPanel devices={devices} />

      <Panel title="Etiquetas" subtitle="Agrupa dispositivos como quieras">
        <TagManager tags={tags} onChanged={refreshTags} />
      </Panel>

      <footer className="pb-4 text-center text-[11px] text-slate-600">
        Router Connections · escanea únicamente la red a la que estás conectado
      </footer>

      {selectedId !== null && (
        <DeviceDrawer
          deviceId={selectedId}
          categories={categories}
          tags={tags}
          onClose={() => setSelectedId(null)}
          onChanged={() => {
            void refreshDevices()
            void refreshTags()
          }}
        />
      )}
    </div>
  )
}
