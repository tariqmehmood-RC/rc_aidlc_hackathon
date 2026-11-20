import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Header() {
  const { user, signOut } = useAuth()
  return (
    <header className="bg-navy text-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-6">
        <Link to="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-sm">IS</span>
          Inside Sales Copilot
        </Link>
        {user && (
          <nav className="text-sm text-blue-100">
            <Link to="/" className="hover:text-white">New brief</Link>
          </nav>
        )}
        <div className="ml-auto flex items-center gap-4 text-sm">
          {user && (
            <>
              {/* BU comes from the signed-in user's token; there is no BU switcher (G1). */}
              <span data-testid="bu-badge" className="rounded-full bg-brand px-3 py-1 text-xs font-semibold">
                BU: {user.bu ?? 'none'}
              </span>
              <span className="text-blue-100">{user.email}</span>
              <button type="button" onClick={() => void signOut()} className="text-blue-200 hover:text-white">Sign out</button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
