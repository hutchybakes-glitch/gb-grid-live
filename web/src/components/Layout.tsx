import type { ReactNode } from 'react'
import { useData, type Meta } from '../lib/data'
import { ukDateTime, ukTime, ukZone } from '../lib/format'
import { setTheme, useTheme } from '../lib/theme'
import { PAGES, type PageId } from '../pages'

interface Props {
  page: PageId
  children: ReactNode
}

function UpdatedBadge() {
  const meta = useData<Meta>('meta.json')
  if (meta.status !== 'ready') return null
  const t = meta.data.data_last_updated
  return (
    <span className="badge" title="When the forecasts on this site were last captured">
      <span className="long">Data last updated {ukDateTime(t)} {ukZone(t)}</span>
      <span className="short">Updated {ukTime(t)}</span>
    </span>
  )
}

export default function Layout({ page, children }: Props) {
  const theme = useTheme()
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="header">
        <div className="header-inner">
          <a className="brand" href="#/now">GB Grid <span>Live</span></a>
          <nav className="nav" aria-label="Pages">
            {PAGES.map((p) => (
              <a key={p.id} href={`#/${p.id}`} aria-current={p.id === page ? 'page' : undefined}>
                {p.label}
              </a>
            ))}
          </nav>
          <div className="header-tools">
            <UpdatedBadge />
            <button
              className="icon-btn"
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </div>
      </header>
      <main id="main">{children}</main>
      <footer className="footer">
        <div className="footer-inner">
          <p>
            Data: <a href="https://carbonintensity.org.uk">Carbon Intensity API</a> by NESO, licensed{' '}
            <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.{' '}
            Solar: <a href="https://www.solar.sheffield.ac.uk/pvlive/">PV_Live</a> by Sheffield Solar, University of Sheffield, funded by NESO.
          </p>
          <p>Independent project, not affiliated with NESO or Sheffield Solar. Times are UK local time unless stated.</p>
        </div>
      </footer>
    </>
  )
}
