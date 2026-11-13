import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { useMemo, useState } from 'react';
import App from './App';
import { makeTheme, type ThemeMode } from './theme';
import { applyThemeMode } from './themeMode';

/** Holds light/dark mode for the MUI theme and the CSS variables. */
export default function Root({ startMode }: { startMode: ThemeMode }) {
  const [mode, setMode] = useState<ThemeMode>(startMode);
  const theme = useMemo(() => makeTheme(mode), [mode]);

  function toggleMode() {
    const next = mode === 'dark' ? 'light' : 'dark';
    applyThemeMode(next); // CSS variables switch before React re-renders
    setMode(next);
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App themeMode={mode} onToggleThemeMode={toggleMode} />
    </ThemeProvider>
  );
}
