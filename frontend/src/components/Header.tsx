import { NavLink } from 'react-router-dom'

export function Header() {
  return (
    <header className="header">
      <div className="header__inner">
        <h1 className="header__title">RAG</h1>
        <span className="header__tagline">RAG with clickable citations</span>
        <nav className="header__nav">
          <NavLink to="/" end className={navClassName}>
            Chat
          </NavLink>
          <NavLink to="/documents" className={navClassName}>
            Documents
          </NavLink>
        </nav>
      </div>
    </header>
  )
}

function navClassName({ isActive }: { isActive: boolean }): string {
  return isActive ? 'header__link header__link--active' : 'header__link'
}
