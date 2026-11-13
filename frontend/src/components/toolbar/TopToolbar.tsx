import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import {
  featureButtonId, HELP_FEATURE, TOOLBAR_FEATURES, type FeatureEntry, type FeatureId,
} from '../../features/features';
import type { MapGame } from '../../services/gameService';
import type { ThemeMode } from '../../theme';
import { MoonIcon, SunIcon } from '../icons';
import SearchBox from './SearchBox';

interface TopToolbarProps {
  games: MapGame[] | null;
  activeFeature: FeatureId | null;
  onToggleFeature: (id: FeatureId) => void;
  onSearchSelect: (game: MapGame) => void;
  themeMode: ThemeMode;
  onToggleThemeMode: () => void;
}

export default function TopToolbar({
  games, activeFeature, onToggleFeature, onSearchSelect, themeMode, onToggleThemeMode,
}: TopToolbarProps) {
  const dark = themeMode === 'dark';
  function renderButton({ id, label, Icon }: FeatureEntry) {
    const active = activeFeature === id;
    return (
      // The text label hides on narrow screens (CSS); the tooltip and
      // aria-label keep the button named.
      <Tooltip key={id} title={label}>
        <Button
          id={featureButtonId(id)}
          className={`tool-button${active ? ' is-active' : ''}`}
          size="small"
          color="inherit"
          aria-label={label}
          aria-expanded={active}
          aria-controls={active ? 'feature-panel' : undefined}
          startIcon={<Icon fontSize="small" />}
          onClick={() => onToggleFeature(id)}
        >
          <span className="tool-label">{label}</span>
        </Button>
      </Tooltip>
    );
  }

  return (
    <header className="top-toolbar">
      <span className="wordmark">Game Map</span>
      <nav className="tool-group" aria-label="Features">
        {TOOLBAR_FEATURES.map(renderButton)}
      </nav>
      <div className="toolbar-right">
        <SearchBox games={games} onSelectGame={onSearchSelect} />
        <Tooltip title={dark ? 'Light mode' : 'Dark mode'}>
          <IconButton
            className="theme-toggle"
            size="small"
            aria-label="Dark mode"
            aria-pressed={dark}
            onClick={onToggleThemeMode}
          >
            {dark ? <SunIcon fontSize="small" /> : <MoonIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        {renderButton(HELP_FEATURE)}
      </div>
    </header>
  );
}
