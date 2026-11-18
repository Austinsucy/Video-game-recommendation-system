import Button from '@mui/material/Button';
import FeaturePanel from './FeaturePanel';

// Only controls that work today. Add a row when a feature ships.
const MAP_CONTROLS: [string, string][] = [
  ['Move around', 'Drag the map, or focus it and use the arrow keys'],
  ['Zoom', 'Scroll, pinch, the zoom buttons, or the + and − keys'],
  ['See every game again', 'Reset view, at the bottom right'],
  ['Game name', 'Hover over a dot'],
  ['Game information', 'Click a dot, or search by title'],
  ['Close a panel', 'Its close button, or Esc'],
];

interface HelpPanelProps {
  onClose: () => void;
  onStartTour: () => void;
}

export default function HelpPanel({ onClose, onStartTour }: HelpPanelProps) {
  return (
    <FeaturePanel
      title="Help"
      requirement="GW 1"
      status="available"
      summary="Each dot is a game. Games with similar genres, mechanics and themes sit close together, and colors mark groups of similar games."
      onClose={onClose}
    >
      <dl className="help-list">
        {MAP_CONTROLS.map(([task, how]) => (
          <div key={task}>
            <dt>{task}</dt>
            <dd>{how}</dd>
          </div>
        ))}
      </dl>
      <div className="panel-actions help-tour-action">
        <Button variant="outlined" size="small" onClick={onStartTour}>Start guided tour</Button>
      </div>
    </FeaturePanel>
  );
}
