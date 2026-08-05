import { useEffect, useState } from 'react'
import { api, Bot, PendingTrade } from '../api'

export default function BotsPage() {
  const [bots, setBots] = useState<Bot[]>([])
  const [trades, setTrades] = useState<PendingTrade[]>([])

  useEffect(() => {
    api.getBots().then(setBots).catch(console.error)
    api.getPendingTrades().then(setTrades).catch(console.error)
  }, [])

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Боты</h2>

      {/* Bots */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {bots.map((bot) => (
          <div key={bot.bot_id} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold">{bot.bot_id}</h3>
              <span className={`px-2 py-1 rounded text-xs ${bot.ws_connected ? 'bg-green-600' : 'bg-red-600'}`}>
                {bot.ws_connected ? 'Online' : 'Offline'}
              </span>
            </div>
            <p className="text-sm text-gray-400">
              Статус: {bot.status}
            </p>
            <p className="text-sm text-gray-400">
              Последний: {bot.last_seen ? new Date(bot.last_seen).toLocaleString('ru-RU') : 'никогда'}
            </p>
          </div>
        ))}
        {bots.length === 0 && (
          <p className="text-gray-500">Нет зарегистрированных ботов</p>
        )}
      </div>

      {/* Pending Trades */}
      <h3 className="text-xl font-bold mb-4">Ожидающие трейды</h3>
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3">ID</th>
              <th className="text-left px-4 py-3">Заказ</th>
              <th className="text-left px-4 py-3">Покупатель</th>
              <th className="text-left px-4 py-3">Предметы</th>
              <th className="text-left px-4 py-3">Бот</th>
              <th className="text-left px-4 py-3">Создан</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr key={trade.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                <td className="px-4 py-3">#{trade.id}</td>
                <td className="px-4 py-3">#{trade.order_id}</td>
                <td className="px-4 py-3">{trade.buyer_nickname}</td>
                <td className="px-4 py-3">{trade.items.join(', ')}</td>
                <td className="px-4 py-3 text-gray-400">{trade.bot_id}</td>
                <td className="px-4 py-3 text-gray-400">
                  {new Date(trade.created_at).toLocaleString('ru-RU')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {trades.length === 0 && (
          <p className="text-center text-gray-500 py-8">Нет ожидающих трейдов</p>
        )}
      </div>
    </div>
  )
}
