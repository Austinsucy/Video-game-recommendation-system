import { createTheme } from '@mui/material/styles';

// One place for the app's colours and type. Text colours meet WCAG AA on
// the light surfaces (ACC 1).
export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#1d4ed8' },
    text: { primary: '#1f2937', secondary: '#4b5563' },
    background: { default: '#f7f7f5', paper: '#ffffff' },
    divider: '#e2e2de',
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
          '&.Mui-focusVisible': { outline: '2px solid #1d4ed8', outlineOffset: 2 },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          '&.Mui-focusVisible': { outline: '2px solid #1d4ed8', outlineOffset: 2 },
        },
      },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
    MuiTooltip: { defaultProps: { arrow: false, enterDelay: 400 } },
  },
});
