import { Building2, Globe, Monitor, Router as RouterIcon, type LucideIcon } from 'lucide-react'

import type { NetworkStatus } from '../api/types'
import { formatRelative } from '../lib/format'
import { Chip, Panel } from './ui'

function Stat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
      <p
        className={`truncate text-sm text-slate-100 ${mono ? 'font-mono' : ''}`}
        title={value}
      >
        {value}
      </p>
    </div>
  )
}

/** Dibuja la cadena de saltos privados para que la topología se vea de un vistazo. */
function TopologyChain({ status }: { status: NetworkStatus }) {
  const topology = status.topology
  if (!topology) return null

  const nodes: { label: string; sub: string; icon: LucideIcon }[] = [
    { label: 'Tu PC', sub: status.interface?.ip ?? '', icon: Monitor },
    ...topology.private_hops.map((ip, index) => ({
      label: index === 0 && topology.kind === 'direct' ? 'Router principal' : `Router ${index + 1}`,
      sub: ip,
      icon: RouterIcon,
    })),
    {
      label: topology.behind_cgnat ? 'CGNAT del ISP' : 'Internet',
      sub: status.public_ip ?? '',
      icon: topology.behind_cgnat ? Building2 : Globe,
    },
  ]

  return (
    <div className="flex flex-wrap items-center gap-2">
      {nodes.map((node, index) => (
        <div key={`${node.label}-${index}`} className="flex items-center gap-2">
          <div className="rounded-xl border border-edge bg-panel-soft/60 px-3 py-2">
            <p className="flex items-center gap-1.5 text-xs font-medium text-slate-200">
              <node.icon className="h-3.5 w-3.5 text-slate-400" strokeWidth={1.75} />
              {node.label}
            </p>
            {node.sub && <p className="font-mono text-[11px] text-slate-400">{node.sub}</p>}
          </div>
          {index < nodes.length - 1 && <span className="text-slate-600">→</span>}
        </div>
      ))}
    </div>
  )
}

export function NetworkPanel({ status }: { status: NetworkStatus | null }) {
  if (!status) {
    return (
      <Panel title="Mi red">
        <p className="text-sm text-slate-400">Cargando información de la red…</p>
      </Panel>
    )
  }

  const { interface: iface, topology } = status

  return (
    <Panel
      title="Mi red"
      subtitle={
        status.last_scan_at ? `Último barrido ${formatRelative(status.last_scan_at)}` : undefined
      }
      actions={
        <>
          <Chip className="bg-emerald-500/15 text-emerald-300 ring-emerald-500/30">
            {status.online_count} en línea
          </Chip>
          <Chip className="bg-slate-500/15 text-slate-300 ring-slate-500/30">
            {status.device_count} conocidos
          </Chip>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="IP local" value={iface?.ip ?? '—'} mono />
        <Stat label="IP pública" value={status.public_ip ?? 'no disponible'} mono />
        <Stat label="Puerta de enlace" value={iface?.gateway ?? '—'} mono />
        <Stat label="Subred" value={iface ? `/${iface.prefix_length}` : '—'} mono />
        <Stat label="Interfaz" value={iface?.name ?? '—'} />
      </div>

      {topology && (
        <div className="mt-5 space-y-3 border-t border-edge/60 pt-4">
          <TopologyChain status={status} />
          <p className="text-xs leading-relaxed text-slate-400">{topology.summary}</p>
        </div>
      )}
    </Panel>
  )
}
