import type { DeviceCategory } from '../api/types'

interface CategoryStyle {
  label: string
  icon: string
  /** Clases de Tailwind para el chip de categoría. */
  chip: string
}

export const CATEGORY_STYLES: Record<DeviceCategory, CategoryStyle> = {
  router: { label: 'Router', icon: '🛜', chip: 'bg-sky-500/15 text-sky-300 ring-sky-500/30' },
  modem: { label: 'Módem', icon: '📡', chip: 'bg-indigo-500/15 text-indigo-300 ring-indigo-500/30' },
  access_point: {
    label: 'Punto de acceso',
    icon: '📶',
    chip: 'bg-cyan-500/15 text-cyan-300 ring-cyan-500/30',
  },
  pc: { label: 'PC', icon: '🖥️', chip: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30' },
  laptop: {
    label: 'Portátil',
    icon: '💻',
    chip: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
  },
  phone: { label: 'Teléfono', icon: '📱', chip: 'bg-violet-500/15 text-violet-300 ring-violet-500/30' },
  tablet: { label: 'Tablet', icon: '📲', chip: 'bg-violet-500/15 text-violet-300 ring-violet-500/30' },
  tv: { label: 'TV', icon: '📺', chip: 'bg-amber-500/15 text-amber-300 ring-amber-500/30' },
  console: { label: 'Consola', icon: '🎮', chip: 'bg-rose-500/15 text-rose-300 ring-rose-500/30' },
  printer: { label: 'Impresora', icon: '🖨️', chip: 'bg-slate-400/15 text-slate-300 ring-slate-400/30' },
  camera: { label: 'Cámara', icon: '📷', chip: 'bg-orange-500/15 text-orange-300 ring-orange-500/30' },
  speaker: { label: 'Altavoz', icon: '🔊', chip: 'bg-pink-500/15 text-pink-300 ring-pink-500/30' },
  nas: { label: 'NAS', icon: '🗄️', chip: 'bg-teal-500/15 text-teal-300 ring-teal-500/30' },
  iot: { label: 'IoT', icon: '💡', chip: 'bg-lime-500/15 text-lime-300 ring-lime-500/30' },
  unknown: {
    label: 'Desconocido',
    icon: '❔',
    chip: 'bg-slate-500/15 text-slate-400 ring-slate-500/30',
  },
}

export function categoryStyle(category: DeviceCategory): CategoryStyle {
  return CATEGORY_STYLES[category] ?? CATEGORY_STYLES.unknown
}
