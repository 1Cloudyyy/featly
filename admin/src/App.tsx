import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import { Package, ShoppingCart, Bot, BarChart3 } from 'lucide-react'
import OrdersPage from './pages/OrdersPage'
import InventoryPage from './pages/InventoryPage'
import BotsPage from './pages/BotsPage'
import StatsPage from './pages/StatsPage'

const nav = [
  { path: '/', label: 'Заказы', icon: ShoppingCart },
  { path: '/inventory', label: 'Инвентарь', icon: Package },
  { path: '/bots', label: 'Боты', icon: Bot },
  { path: '/stats', label: 'Статистика', icon: BarChart3 },
]

function Sidebar() {
  const location = useLocation()
  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 min-h-screen p-4">
      <h1 className="text-xl font-bold mb-8 text-blue-400">Featly Admin</h1>
      <nav className="space-y-1">
        {nav.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
              location.pathname === path
                ? 'bg-gray-800 text-white'
                : 'text-gray-400 hover:bg-gray-800/50 hover:text-white'
            }`}
          >
            <Icon size={18} />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <Routes>
            <Route path="/" element={<OrdersPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/bots" element={<BotsPage />} />
            <Route path="/stats" element={<StatsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
