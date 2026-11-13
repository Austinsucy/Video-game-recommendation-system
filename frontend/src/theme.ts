import { createTheme } from '@mui/material/styles';

export type ThemeMode = 'light' | 'dark';

// Keep these in step with the CSS variables in app.css.
const PALETTES = {
  light: {
    accent: '#1d4ed8',
    text: { primary: '#1f2937', secondary: '#4b5563' },
    background: { default: '#f7f7f5', paper: '#ffffff' },
    divider: '#e2e2de',
  },
  dark: {
    accent: '#7ea2ff',
    text: { primary: '#e6e8ec', secondary: '#a3abb9' },
    background: { default: '#12151b', paper: '#1b1f27' },
    divider: '#2c323d',
  },
};

// One place for the app's colours and type. Text colours meet WCAG AA on
// the surfaces of both modes (ACC 1).
export function makeTheme(mode: ThemeMode) {
  const { accent, text, background, divider } = PALETTES[mode];
  return createTheme({
    palette: {
      mode,
      primary: { main: accent },
      text,
      background,
      divider,
    },
    shape: { borderRadius: 6 },
    typography: {
      fontFamily: '"Inter", "Segoe UI", system-ui, -apple-system, sans-serif',
      fontSize: 13,
      button: { textTransform: 'none', fontWeight: 500 },
    },
    components: {
      MuiButtonBase: { defaultProps: { disableRipple: true } },
      MuiButton: {
        styleOverrides: {
          root: {
            '&.Mui-focusVisible': { outline: `2px solid ${accent}`, outlineOffset: 2 },
          },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: {
            '&.Mui-focusVisible': { outline: `2px solid ${accent}`, outlineOffset: 2 },
          },
        },
      },
      MuiPaper: { defaultProps: { elevation: 0 } },
      MuiTooltip: { defaultProps: { arrow: false, enterDelay: 400 } },
    },
  });
}
