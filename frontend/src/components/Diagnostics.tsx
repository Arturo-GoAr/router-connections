import { AlertTriangle, Info, X } from 'lucide-react'
import { useState } from 'react'

import type { Diagnostic } from '../api/types'

/** Avisos sobre limitaciones del entorno (perfil de red, permisos, etc.). */
export function Diagnostics({ items }: { items: Diagnostic[] }) {
  const [dismissed, setDismissed] = useState<string[]>([])
  const visible = items.filter((item) => !dismissed.includes(item.title))

  if (!visible.length) return null

  return (
    <div className="space-y-2">
      {visible.map((item) => {
        const isWarning = item.level === 'warning'
        return (
          <div
            key={item.title}
            className={`flex items-start gap-3 rounded-xl border px-4 py-3 ${
              isWarning
                ? 'border-amber-500/30 bg-amber-500/10'
                : 'border-edge/70 bg-panel/60'
            }`}
          >
            {isWarning ? (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" strokeWidth={1.75} />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" strokeWidth={1.75} />
            )}
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-medium ${isWarning ? 'text-amber-200' : 'text-slate-200'}`}>
                {item.title}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{item.detail}</p>
            </div>
            <button
              onClick={() => setDismissed((previous) => [...previous, item.title])}
              className="rounded px-1.5 text-slate-500 transition-colors hover:text-slate-300"
              aria-label="Descartar aviso"
            >
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
