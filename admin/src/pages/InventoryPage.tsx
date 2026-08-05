import { useEffect, useState } from 'react'
import { api, InventoryItem } from '../api'

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [editing, setEditing] = useState<string | null>(null)
  const [editCount, setEditCount] = useState(0)

  useEffect(() => {
    api.getInventory().then(setItems).catch(console.error)
  }, [])

  const handleSave = async (key: string) => {
    await api.updateItem(key, { count: editCount })
    setItems((prev) =>
      prev.map((i) => (i.item_key === key ? { ...i, count: editCount } : i))
    )
    setEditing(null)
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Инвентарь</h2>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left px-4 py-3">Ключ</th>
              <th className="text-left px-4 py-3">Название</th>
              <th className="text-left px-4 py-3">Кол-во</th>
              <th className="text-left px-4 py-3">Порог</th>
              <th className="text-left px-4 py-3">Обновлён</th>
              <th className="text-left px-4 py-3">Действия</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                <td className="px-4 py-3 font-mono text-xs">{item.item_key}</td>
                <td className="px-4 py-3">{item.name}</td>
                <td className="px-4 py-3">
                  {editing === item.item_key ? (
                    <input
                      type="number"
                      value={editCount}
                      onChange={(e) => setEditCount(Number(e.target.value))}
                      className="bg-gray-800 border border-gray-600 rounded px-2 py-1 w-20"
                    />
                  ) : (
                    <span className={item.count <= item.low_stock_threshold ? 'text-yellow-400' : ''}>
                      {item.count}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-400">{item.low_stock_threshold}</td>
                <td className="px-4 py-3 text-gray-400">
                  {new Date(item.updated_at).toLocaleString('ru-RU')}
                </td>
                <td className="px-4 py-3">
                  {editing === item.item_key ? (
                    <button
                      onClick={() => handleSave(item.item_key)}
                      className="text-green-400 hover:text-green-300 text-xs"
                    >
                      Сохранить
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        setEditing(item.item_key)
                        setEditCount(item.count)
                      }}
                      className="text-blue-400 hover:text-blue-300 text-xs"
                    >
                      Изменить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && (
          <p className="text-center text-gray-500 py-8">Инвентарь пуст</p>
        )}
      </div>
    </div>
  )
}
