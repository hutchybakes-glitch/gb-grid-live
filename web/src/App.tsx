import { useEffect, useState } from 'react'
import Layout from './components/Layout'
import { PAGES, pageFromHash, type PageId } from './pages'
import Now from './pages/Now'
import Explore from './pages/Explore'
import How from './pages/How'
import Plan from './pages/Plan'
import Trust from './pages/Trust'

// Hash routing: works on any static host (GitHub Pages included) with no server rewrites.
function usePage(): PageId {
  const [page, setPage] = useState<PageId>(() => pageFromHash(window.location.hash))
  useEffect(() => {
    const onHash = () => {
      setPage(pageFromHash(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return page
}

export default function App() {
  const page = usePage()
  const title = PAGES.find((p) => p.id === page)!.title
  useEffect(() => {
    document.title = `${title} · GB Grid Live`
  }, [title])

  return (
    <Layout page={page}>
      {page === 'now' && <Now />}
      {page === 'plan' && <Plan />}
      {page === 'trust' && <Trust />}
      {page === 'explore' && <Explore />}
      {page === 'how' && <How />}
    </Layout>
  )
}
