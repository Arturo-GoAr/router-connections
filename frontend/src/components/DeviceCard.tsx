import type { Device } from '../api/types'
import { categoryStyle } from '../lib/categories'
import { formatRelative, formatUptime } from '../lib/format'
import { Chip } from './ui'

export function DeviceCard({
  device,
  selected,
  onSelect,
}: {
  device: Device
  selected: boolean
  onSelect: (device: Device) => void
}) {
  const style = categoryStyle(device.category)

  return (
    <button
      onClick={() => onSelect(device)}
      className={`w-full rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:border-sky-500/50 hover:shadow-lg hover:shadow-sky-950/40 ${
        selected ? 'border-sky-500/70 bg-panel-soft/80' : 'border-edge/70 bg-panel/60'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl leading-none">{style.icon}</span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                device.is_online ? 'bg-emerald-400' : 'bg-slate-600'
              }`}
              title={device.is_online ? 'En línea' : 'Desconectado'}
            />
            <p className="truncate text-sm font-semibold text-slate-100" title={device.display_name}>
              {device.display_name}
            </p>
            {device.is_favorite && <span className="text-xs text-amber-300">★</span>}
          </div>

          <p className="mt-0.5 truncate font-mono text-xs text-slate-400">
            {device.ip ?? 'sin IP'} · {device.mac}
          </p>

          {device.vendor && (
            <p className="mt-1 truncate text-xs text-slate-500" title={device.vendor}>
              {device.vendor}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Chip className={style.chip}>{style.label}</Chip>

        {device.is_gateway && (
          <Chip className="bg-sky-500/15 text-sky-300 ring-sky-500/30">Puerta de enlace</Chip>
        )}
        {device.is_self && (
          <Chip className="bg-emerald-500/15 text-emerald-300 ring-emerald-500/30">Este equipo</Chip>
        )}
        {device.open_port_count > 0 && (
          <Chip className="bg-amber-500/15 text-amber-300 ring-amber-500/30">
            {device.open_port_count} {device.open_port_count === 1 ? 'puerto' : 'puertos'}
          </Chip>
        )}
        {device.tags.map((tag) => (
          <Chip
            key={tag.id}
            className="ring-transparent"
            // El color lo elige el usuario, así que va inline en vez de por clase.
            {...{ style: { backgroundColor: `${tag.color}22`, color: tag.color } }}
          >
            {tag.name}
          </Chip>
        ))}
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        {device.is_online
          ? `Conectado desde hace ${formatUptime(device.uptime_seconds)}`
          : `Visto por última vez ${formatRelative(device.last_seen)}`}
      </p>
    </button>
  )
}
