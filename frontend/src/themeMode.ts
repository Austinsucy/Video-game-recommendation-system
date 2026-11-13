import type { ThemeMode } from './theme';

const STORAGE_KEY = 'game-map-theme';

/** The saved choice, or the system setting the first time. */
export function initialThemeMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // Storage can be blocked; fall back to the system setting.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Switches the CSS variables in app.css and remembers the choice. */
export function applyThemeMode(mode: ThemeMode) {
  document.documentElement.dataset.theme = mode;
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // Not saved; the choice still applies until the page is closed.
  }
}
