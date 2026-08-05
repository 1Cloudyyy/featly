import { useEffect, useState } from 'react'
import { api, Order } from '../api'

const statusColors: Record<string, string> = {
  new: 'bg-gray-600',
  dialog: 'bg-yellow-600',
  waiting_trade: 'bg-blue-600',
  delivering: 'bg-purple-600',
  completed: 'bg-green-600',
  cancelled: 'bg-red-600',
  refunded: 'bg-red-800',
}

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [filter, setFilter] = useState('')

  useEffect(() => {
    api.getOrders().then(setOrders).catch(console.error)
  }, [])

  const filtered = filter
    ? orders.filter((o) => o.status === filter)
    : orders

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Заказы</h2>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">Все</option>
          <option value="waiting_trade">Ожидание трейда</option>
          <option value="delivering">Выдача</option>
          <option value="completed">Выполнено</option>
          <option value="cancelled">Отменено</option>
        </select>
      </div>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3">ID</th>
              <th className="text-left px-4 py-3">FunPay</th>
              <th className="text-left px-4 py-3">Покупатель</th>
              <th className="text-left px-4 py-3">Предметы</th>
              <th className="text-left px-4 py-3">Статус</th>
              <th className="text-left px-4 py-3">Создан</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((order) => (
              <tr key={order.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                <td className="px-4 py-3">#{order.id}</td>
                <td className="px-4 py-3 text-gray-400">{order.funpay_order_id}</td>
                <td className="px-4 py-3">{order.buyer_nickname}</td>
                <td className="px-4 py-3">{order.items.join(', ')}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs ${statusColors[order.status] || 'bg-gray-600'}`}>
                    {order.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400">
                  {new Date(order.created_at).toLocaleString('ru-RU')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-center text-gray-500 py-8">Нет заказов</p>
        )}
      </div>
    </div>
  )
}
