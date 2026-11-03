import Button from '@mui/material/Button';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

// Only controls that work today. Add a row when a feature ships.
const MAP_CONTROLS: [string, string][] = [
  ['Move around', 'Drag the map, or focus it and use the arrow keys'],
  ['Zoom', 'Scroll, pinch, the zoom buttons, or the + and − keys'],
  ['See every game again', 'Reset view, at the bottom right'],
  ['Game name', 'Hover over a dot'],
  ['Game information', 'Click a dot, or search by title'],
  ['Close a panel', 'Its close button, or Esc'],
];

export default function HelpPanel({ onClose }: { onClose: () => void }) {
  return (
    <FeaturePanel
      title="Help"
      requirement="GW 1"
      status="partial"
      summary="Each dot is a game. Games with similar genres, mechanics and themes sit close together, and colours mark groups of similar games."
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
      <PlannedControls note="A step-by-step guided tour is not available yet.">
        <div className="panel-actions">
          <Button variant="outlined" size="small" disabled>Start guided tour</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
