import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import Root from './Root.tsx'
import { initialThemeMode } from './themeMode.ts'

const startMode = initialThemeMode()
document.documentElement.dataset.theme = startMode // before the first paint, so there is no flash

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root startMode={startMode} />
  </StrictMode>,
)
