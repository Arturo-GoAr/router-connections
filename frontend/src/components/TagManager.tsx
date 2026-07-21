import { X } from 'lucide-react'
import { useState } from 'react'

import { api } from '../api/client'
import type { Tag } from '../api/types'
import { Button, ErrorNote, Input } from './ui'

const PALETTE = ['#38bdf8', '#34d399', '#fbbf24', '#f472b6', '#a78bfa', '#f87171']

export function TagManager({ tags, onChanged }: { tags: Tag[]; onChanged: () => void }) {
  const [name, setName] = useState('')
  const [color, setColor] = useState(PALETTE[0])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.createTag(name.trim(), color)
      setName('')
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (tag: Tag) => {
    setBusy(true)
    setError(null)
    try {
      await api.deleteTag(tag.id)
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={create} className="flex flex-wrap items-center gap-2">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Nueva etiqueta"
          className="max-w-48"
        />
        <div className="flex gap-1">
          {PALETTE.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setColor(option)}
              className={`h-6 w-6 rounded-full transition-transform ${
                color === option ? 'scale-110 ring-2 ring-white/60' : 'opacity-60 hover:opacity-100'
              }`}
              style={{ backgroundColor: option }}
              aria-label={`Color ${option}`}
            />
          ))}
        </div>
        <Button type="submit" loading={busy}>
          Añadir
        </Button>
      </form>

      {error && <ErrorNote message={error} />}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={tag.id}
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
              style={{ backgroundColor: `${tag.color}22`, color: tag.color }}
            >
              {tag.name}
              <button
                onClick={() => remove(tag)}
                className="opacity-60 transition-opacity hover:opacity-100"
                aria-label={`Borrar etiqueta ${tag.name}`}
              >
                <X className="h-3 w-3" strokeWidth={2} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
