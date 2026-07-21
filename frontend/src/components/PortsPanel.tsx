import { Inbox, Plug, Shield, ShieldOff } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Device, FirewallRule, FirewallStatus, PortMapping, UpnpStatus } from '../api/types'
import { Button, EmptyState, ErrorNote, Field, Input, Panel, Select, Spinner } from './ui'

type TabKey = 'upnp' | 'firewall'

/**
 * Gestión de puertos en dos frentes distintos, que la interfaz separa a
 * propósito porque hacen cosas muy distintas:
 *
 * - **Router (UPnP)**: abre el puerto hacia internet. Es lo que la gente llama
 *   "abrir un puerto".
 * - **Firewall de Windows**: solo afecta a este equipo dentro de la red local.
 */
export function PortsPanel({ devices }: { devices: Device[] }) {
  const [tab, setTab] = useState<TabKey>('upnp')

  return (
    <Panel
      title="Gestión de puertos"
      actions={
        <div className="flex rounded-lg border border-edge bg-surface/60 p-0.5 text-xs">
          {(
            [
              ['upnp', 'Router (UPnP)'],
              ['firewall', 'Firewall de Windows'],
            ] as [TabKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-md px-3 py-1 font-medium transition-colors ${
                tab === key ? 'bg-sky-500/90 text-slate-950' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      }
    >
      {tab === 'upnp' ? <UpnpTab devices={devices} /> : <FirewallTab />}
    </Panel>
  )
}

function UpnpTab({ devices }: { devices: Device[] }) {
  const [status, setStatus] = useState<UpnpStatus | null>(null)
  const [mappings, setMappings] = useState<PortMapping[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [externalPort, setExternalPort] = useState('')
  const [internalPort, setInternalPort] = useState('')
  const [client, setClient] = useState('')
  const [protocol, setProtocol] = useState('TCP')
  const [description, setDescription] = useState('')

  const load = async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const current = await api.upnpStatus(refresh)
      setStatus(current)
      setMappings(current.available ? await api.listMappings() : [])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createMapping({
        external_port: Number(externalPort),
        internal_port: Number(internalPort || externalPort),
        internal_client: client,
        protocol,
        description: description || 'Router Connections',
      })
      setExternalPort('')
      setInternalPort('')
      setDescription('')
      setMappings(await api.listMappings())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (mapping: PortMapping) => {
    setBusy(true)
    setError(null)
    try {
      await api.deleteMapping(mapping.protocol, mapping.external_port)
      setMappings(await api.listMappings())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-sm text-slate-400">
        <Spinner /> Buscando un router compatible con UPnP…
      </p>
    )
  }

  if (!status?.available) {
    return (
      <div className="space-y-3">
        <EmptyState
          icon={Plug}
          title="UPnP no está disponible en tu router"
          detail={status?.reason ?? undefined}
        />
        <div className="flex justify-center">
          <Button onClick={() => load(true)}>Reintentar búsqueda</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-edge/70 bg-panel-soft/40 px-4 py-3 text-xs">
        <p className="text-slate-200">
          {status.router_name ?? 'Router'}
          {status.router_model && <span className="text-slate-400"> · {status.router_model}</span>}
        </p>
        {status.external_ip && (
          <p className="mt-0.5 font-mono text-slate-400">IP externa: {status.external_ip}</p>
        )}
      </div>

      {error && <ErrorNote message={error} />}

      <form onSubmit={create} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Puerto externo">
          <Input
            required
            type="number"
            min={1}
            max={65535}
            value={externalPort}
            onChange={(event) => setExternalPort(event.target.value)}
            placeholder="8080"
          />
        </Field>
        <Field label="Puerto interno" hint="Vacío = mismo que el externo">
          <Input
            type="number"
            min={1}
            max={65535}
            value={internalPort}
            onChange={(event) => setInternalPort(event.target.value)}
            placeholder={externalPort || '8080'}
          />
        </Field>
        <Field label="Equipo destino">
          <Select required value={client} onChange={(event) => setClient(event.target.value)}>
            <option value="">Elige un dispositivo…</option>
            {devices
              .filter((device) => device.ip)
              .map((device) => (
                <option key={device.id} value={device.ip!}>
                  {device.display_name} ({device.ip})
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Protocolo">
          <Select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
            <option>TCP</option>
            <option>UDP</option>
          </Select>
        </Field>
        <Field label="Descripción">
          <div className="flex gap-2">
            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Servidor web"
            />
            <Button type="submit" variant="primary" loading={busy}>
              Abrir
            </Button>
          </div>
        </Field>
      </form>

      {mappings.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No hay puertos redirigidos"
          detail="Cuando crees una redirección, aparecerá aquí y el puerto quedará accesible desde internet."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-xs">
            <thead className="text-slate-500">
              <tr className="border-b border-edge/60">
                <th className="pb-2 font-medium">Externo</th>
                <th className="pb-2 font-medium">→ Interno</th>
                <th className="pb-2 font-medium">Equipo</th>
                <th className="pb-2 font-medium">Proto</th>
                <th className="pb-2 font-medium">Descripción</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-edge/40">
              {mappings.map((mapping) => (
                <tr key={`${mapping.protocol}-${mapping.external_port}`}>
                  <td className="py-2 font-mono text-sky-300">{mapping.external_port}</td>
                  <td className="py-2 font-mono text-slate-300">{mapping.internal_port}</td>
                  <td className="py-2 font-mono text-slate-400">{mapping.internal_client}</td>
                  <td className="py-2 text-slate-400">{mapping.protocol}</td>
                  <td className="py-2 text-slate-400">{mapping.description || '—'}</td>
                  <td className="py-2 text-right">
                    <Button variant="danger" onClick={() => remove(mapping)} disabled={busy}>
                      Cerrar
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function FirewallTab() {
  const [status, setStatus] = useState<FirewallStatus | null>(null)
  const [rules, setRules] = useState<FirewallRule[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [name, setName] = useState('')
  const [ports, setPorts] = useState('')
  const [protocol, setProtocol] = useState('TCP')
  const [action, setAction] = useState('Allow')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const current = await api.firewallStatus()
      setStatus(current)
      setRules(current.available ? await api.listFirewallRules(true) : [])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createFirewallRule({
        display_name: name,
        ports,
        protocol,
        direction: 'Inbound',
        action,
        description: 'Creada desde Router Connections',
      })
      setName('')
      setPorts('')
      setRules(await api.listFirewallRules(true))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (rule: FirewallRule) => {
    setBusy(true)
    setError(null)
    try {
      await api.deleteFirewallRule(rule.display_name)
      setRules(await api.listFirewallRules(true))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-sm text-slate-400">
        <Spinner /> Consultando el Firewall de Windows…
      </p>
    )
  }

  if (!status?.available) {
    return <EmptyState icon={ShieldOff} title="Firewall no disponible" detail={status?.reason ?? undefined} />
  }

  return (
    <div className="space-y-4">
      {!status.is_admin && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {status.reason}
        </p>
      )}

      {error && <ErrorNote message={error} />}

      <form onSubmit={create} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Nombre de la regla">
          <Input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Servidor de desarrollo"
          />
        </Field>
        <Field label="Puertos" hint="Ej. 8080, 80,443 o 8000-8100">
          <Input
            required
            value={ports}
            onChange={(event) => setPorts(event.target.value)}
            placeholder="8080"
          />
        </Field>
        <Field label="Protocolo">
          <Select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
            <option>TCP</option>
            <option>UDP</option>
          </Select>
        </Field>
        <Field label="Acción">
          <div className="flex gap-2">
            <Select value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="Allow">Permitir</option>
              <option value="Block">Bloquear</option>
            </Select>
            <Button type="submit" variant="primary" loading={busy} disabled={!status.is_admin}>
              Crear
            </Button>
          </div>
        </Field>
      </form>

      {rules.length === 0 ? (
        <EmptyState
          icon={Shield}
          title="Sin reglas creadas desde esta app"
          detail="Por seguridad, Router Connections solo lista y borra las reglas que ella misma ha creado; las reglas del sistema no se tocan."
        />
      ) : (
        <ul className="divide-y divide-edge/40 overflow-hidden rounded-xl border border-edge/70">
          {rules.map((rule) => (
            <li key={rule.name} className="flex items-center gap-3 px-3 py-2 text-xs">
              <span
                className={`h-2 w-2 rounded-full ${
                  rule.action === 'Allow' ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-slate-200">{rule.display_name}</p>
                <p className="font-mono text-[11px] text-slate-500">
                  {rule.protocol ?? '—'} {rule.local_ports ?? ''} · {rule.direction}
                </p>
              </div>
              <Button variant="danger" onClick={() => remove(rule)} disabled={busy || !status.is_admin}>
                Borrar
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
