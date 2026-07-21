export type DeviceCategory =
  | 'router'
  | 'modem'
  | 'access_point'
  | 'pc'
  | 'laptop'
  | 'phone'
  | 'tablet'
  | 'tv'
  | 'console'
  | 'printer'
  | 'camera'
  | 'speaker'
  | 'nas'
  | 'iot'
  | 'unknown'

export interface Tag {
  id: number
  name: string
  color: string
}

export interface Port {
  id: number
  port: number
  protocol: string
  state: 'open' | 'closed'
  service: string | null
  banner: string | null
  first_seen: string
  last_seen: string
}

export interface DeviceSession {
  id: number
  ip: string | null
  started_at: string
  ended_at: string | null
  duration_seconds: number
}

export interface Device {
  id: number
  mac: string
  ip: string | null
  display_name: string
  hostname: string | null
  friendly_name: string | null
  alias: string | null
  vendor: string | null
  model: string | null
  category: DeviceCategory
  detected_category: DeviceCategory
  category_override: DeviceCategory | null
  detection_reason: string | null
  detection_confidence: number
  notes: string | null
  is_favorite: boolean
  is_gateway: boolean
  is_self: boolean
  is_online: boolean
  first_seen: string
  last_seen: string
  last_port_scan: string | null
  connected_since: string | null
  uptime_seconds: number | null
  open_port_count: number
  tags: Tag[]
}

export interface DeviceDetail extends Device {
  ports: Port[]
  recent_sessions: DeviceSession[]
}

export interface Hop {
  ttl: number
  ip: string | null
  rtt_ms: number | null
  is_private: boolean
  is_cgnat: boolean
}

export interface Topology {
  kind: 'direct' | 'cascade' | 'unknown'
  private_hops: string[]
  behind_cgnat: boolean
  summary: string
  hops: Hop[]
}

export interface NetworkInterface {
  name: string
  ip: string
  prefix_length: number
  cidr: string
  mac: string | null
  gateway: string | null
  dns_servers: string[]
}

export interface Diagnostic {
  level: 'info' | 'warning'
  title: string
  detail: string
}

export interface NetworkStatus {
  interface: NetworkInterface | null
  public_ip: string | null
  topology: Topology | null
  network_profile: string | null
  is_admin: boolean
  is_scanning: boolean
  device_count: number
  online_count: number
  last_scan_at: string | null
  diagnostics: Diagnostic[]
}

export interface ScanResult {
  devices_found: number
  new_devices: number
  went_offline: number
  duration_seconds: number
  errors: string[]
}

export interface UpnpStatus {
  available: boolean
  reason: string | null
  router_name: string | null
  router_model: string | null
  manufacturer: string | null
  external_ip: string | null
}

export interface PortMapping {
  external_port: number
  internal_port: number
  internal_client: string
  protocol: string
  description: string
  enabled: boolean
  lease_duration: number
}

export interface FirewallStatus {
  available: boolean
  is_admin: boolean
  reason: string | null
}

export interface FirewallRule {
  name: string
  display_name: string
  direction: string
  action: string
  enabled: boolean
  protocol: string | null
  local_ports: string | null
  profile: string | null
  description: string | null
  managed: boolean
}

export interface CategoryOption {
  value: DeviceCategory
  label: string
}
