import { useEffect, useState } from 'react'
import { api, Order } from '../api'

export default function StatsPage() {
  const [orders, setOrders] = useState<Order[]>([])

  useEffect(() => {
    api.getOrders().then(setOrders).catch(console.error)
  }, [])

  const completed = orders.filter((o) => o.status === 'completed').length
  const cancelled = orders.filter((o) => o.status === 'cancelled').length
  const active = orders.filter((o) =>
    ['waiting_trade', 'delivering', 'dialog'].includes(o.status)
  ).length

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Статистика</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <StatCard label="Активные" value={active} color="blue" />
        <StatCard label="Выполнено" value={completed} color="green" />
        <StatCard label="Отменено" value={cancelled} color="red" />
      </div>

      <h3 className="text-xl font-bold mb-4">Последние заказы</h3>
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3">ID</th>
              <th className="text-left px-4 py-3">Покупатель</th>
              <th className="text-left px-4 py-3">Статус</th>
              <th className="text-left px-4 py-3">Создан</th>
            </tr>
          </thead>
          <tbody>
            {orders.slice(0, 10).map((order) => (
              <tr key={order.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                <td className="px-4 py-3">#{order.id}</td>
                <td className="px-4 py-3">{order.buyer_nickname}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs ${
                    order.status === 'completed' ? 'bg-green-600' :
                    order.status === 'cancelled' ? 'bg-red-600' : 'bg-gray-600'
                  }`}>
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
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    blue: 'border-blue-600 text-blue-400',
    green: 'border-green-600 text-green-400',
    red: 'border-red-600 text-red-400',
  }
  return (
    <div className={`bg-gray-900 rounded-lg border ${colors[color]} p-4`}>
      <p className="text-sm text-gray-400 mb-1">{label}</p>
      <p className="text-3xl font-bold">{value}</p>
    </div>
  )
}
