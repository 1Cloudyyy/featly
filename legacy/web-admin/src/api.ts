const API_BASE = '/api'

export interface Order {
  id: number
  funpay_order_id: string
  buyer_nickname: string
  buyer_user_id: number
  items: string[]
  status: string
  proof_url: string | null
  created_at: string
  completed_at: string | null
}

export interface InventoryItem {
  id: number
  item_key: string
  name: string
  count: number
  low_stock_threshold: number
  updated_at: string
}

export interface Bot {
  bot_id: string
  status: string
  ws_connected: boolean
  last_seen: string | null
}

export interface PendingTrade {
  id: number
  order_id: number
  bot_id: string
  buyer_nickname: string
  buyer_user_id: number
  items: string[]
  status: string
  created_at: string
}

// API key for backend auth. Set via VITE_API_KEY env (dev) or injected at build.
const API_KEY = (import.meta as any).env?.VITE_API_KEY || ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY
  }

  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  // Orders
  getOrders: () => request<Order[]>('/orders'),
  getOrder: (id: number) => request<Order>(`/orders/${id}`),
  updateOrderStatus: (id: number, status: string) =>
    request<Order>(`/orders/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  // Inventory
  getInventory: () => request<InventoryItem[]>('/inventory'),
  updateItem: (key: string, data: Partial<InventoryItem>) =>
    request<InventoryItem>(`/inventory/${key}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Bots
  getBots: () => request<Bot[]>('/bots'),
  getBot: (id: string) => request<Bot>(`/bots/${id}`),

  // Pending Trades
  getPendingTrades: (botId?: string) =>
    request<PendingTrade[]>(`/pending_trades${botId ? `?bot_id=${botId}` : ''}`),
  deletePendingTrade: (id: number) =>
    request<void>(`/pending_trades/${id}`, { method: 'DELETE' }),
}
