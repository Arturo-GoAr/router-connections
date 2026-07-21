import type {
  CategoryOption,
  Device,
  DeviceCategory,
  DeviceDetail,
  DeviceSession,
  FirewallRule,
  FirewallStatus,
  NetworkStatus,
  Port,
  PortMapping,
  ScanResult,
  Tag,
  UpnpStatus,
} from './types'

/** Error de la API que conserva el mensaje que envió el backend. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError(
      'No se pudo contactar con el servidor. ¿Está corriendo el backend?',
      0,
    )
  }

  if (!response.ok) {
    // FastAPI devuelve `{detail: ...}`; si no, nos quedamos con el texto crudo.
    let detail = `Error ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) detail = body.detail[0]?.msg ?? detail
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  body: JSON.stringify(body),
})

export const api = {
  // --- Red ---
  getNetwork: () => request<NetworkStatus>('/network'),
  scan: (scanPorts: boolean, portProfile = 'quick') =>
    request<ScanResult>('/scan', json({ scan_ports: scanPorts, port_profile: portProfile })),

  // --- Dispositivos ---
  listDevices: (params: { online?: boolean; category?: string; q?: string } = {}) => {
    const search = new URLSearchParams()
    if (params.online !== undefined) search.set('online', String(params.online))
    if (params.category) search.set('category', params.category)
    if (params.q) search.set('q', params.q)
    const query = search.toString()
    return request<Device[]>(`/devices${query ? `?${query}` : ''}`)
  },
  getDevice: (id: number) => request<DeviceDetail>(`/devices/${id}`),
  updateDevice: (
    id: number,
    payload: {
      alias?: string | null
      notes?: string | null
      category_override?: DeviceCategory | null
      is_favorite?: boolean
      clear_category_override?: boolean
    },
  ) =>
    request<DeviceDetail>(`/devices/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    }),
  deleteDevice: (id: number) => request<void>(`/devices/${id}`, { method: 'DELETE' }),
  deviceSessions: (id: number) => request<DeviceSession[]>(`/devices/${id}/sessions`),
  scanPorts: (id: number, profile = 'common') =>
    request<Port[]>(`/devices/${id}/scan-ports?profile=${profile}`, { method: 'POST' }),
  categories: () => request<CategoryOption[]>('/devices/categories'),

  // --- Etiquetas ---
  listTags: () => request<Tag[]>('/tags'),
  createTag: (name: string, color: string) => request<Tag>('/tags', json({ name, color })),
  deleteTag: (id: number) => request<void>(`/tags/${id}`, { method: 'DELETE' }),
  attachTag: (deviceId: number, tagId: number) =>
    request<DeviceDetail>(`/devices/${deviceId}/tags/${tagId}`, { method: 'POST' }),
  detachTag: (deviceId: number, tagId: number) =>
    request<DeviceDetail>(`/devices/${deviceId}/tags/${tagId}`, { method: 'DELETE' }),

  // --- UPnP ---
  upnpStatus: (refresh = false) =>
    request<UpnpStatus>(`/upnp/status${refresh ? '?refresh=true' : ''}`),
  listMappings: () => request<PortMapping[]>('/upnp/mappings'),
  createMapping: (payload: {
    external_port: number
    internal_port: number
    internal_client: string
    protocol: string
    description: string
  }) => request<PortMapping>('/upnp/mappings', json(payload)),
  deleteMapping: (protocol: string, externalPort: number) =>
    request<void>(`/upnp/mappings/${protocol}/${externalPort}`, { method: 'DELETE' }),

  // --- Firewall ---
  firewallStatus: () => request<FirewallStatus>('/firewall/status'),
  listFirewallRules: (onlyManaged = true) =>
    request<FirewallRule[]>(`/firewall/rules?only_managed=${onlyManaged}`),
  createFirewallRule: (payload: {
    display_name: string
    ports: string
    protocol: string
    direction: string
    action: string
    description: string
  }) => request<FirewallRule>('/firewall/rules', json(payload)),
  deleteFirewallRule: (displayName: string) =>
    request<void>(`/firewall/rules/${encodeURIComponent(displayName)}`, {
      method: 'DELETE',
    }),
}
