import { useEffect, useRef, useState } from 'react'

export interface LiveEvent {
  type: string
  payload: unknown
}

/**
 * Conexión WebSocket con el backend, con reconexión automática.
 *
 * El servidor manda `ping` cada 25 s; no hace falta responder, pero sirve para
 * saber que la conexión sigue viva.
 */
export function useLiveEvents(onEvent: (event: LiveEvent) => void) {
  const [connected, setConnected] = useState(false)
  // La referencia evita que un cambio de callback reabra el socket en cada render.
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let attempt = 0
    let closedByUs = false

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(`${protocol}//${window.location.host}/ws`)

      socket.onopen = () => {
        attempt = 0
        setConnected(true)
      }

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as LiveEvent
          if (event.type !== 'ping') handlerRef.current(event)
        } catch {
          /* mensaje no-JSON: se ignora */
        }
      }

      socket.onclose = () => {
        setConnected(false)
        if (closedByUs) return
        // Retroceso exponencial con techo de 15 s para no martillear al backend
        // mientras está reiniciándose.
        attempt += 1
        const delay = Math.min(1000 * 2 ** (attempt - 1), 15000)
        reconnectTimer = window.setTimeout(connect, delay)
      }

      socket.onerror = () => socket?.close()
    }

    connect()

    return () => {
      closedByUs = true
      window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [])

  return { connected }
}
