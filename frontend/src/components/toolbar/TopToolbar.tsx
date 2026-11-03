import Button from '@mui/material/Button';
import Tooltip from '@mui/material/Tooltip';
import {
  featureButtonId, HELP_FEATURE, TOOLBAR_FEATURES, type FeatureEntry, type FeatureId,
} from '../../features/features';
import type { MapGame } from '../../services/gameService';
import SearchBox from './SearchBox';

interface TopToolbarProps {
  games: MapGame[] | null;
  activeFeature: FeatureId | null;
  onToggleFeature: (id: FeatureId) => void;
  onSearchSelect: (game: MapGame) => void;
}

export default function TopToolbar({ games, activeFeature, onToggleFeature, onSearchSelect }: TopToolbarProps) {
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
        {renderButton(HELP_FEATURE)}
      </div>
    </header>
  );
}
