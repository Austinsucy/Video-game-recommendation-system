import Button from '@mui/material/Button';
import Slider from '@mui/material/Slider';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

// UDR 1 categories, in the order the requirements list them.
const CATEGORIES = [
  'Gameplay', 'Mechanics', 'Genre', 'Structure', 'Theme',
  'Multiplayer', 'Perspective', 'Platform', 'Playtime',
];

export default function RecommendationsPanel({ onClose }: { onClose: () => void }) {
  return (
    <FeaturePanel
      title="Recommendations"
      requirement="UDR 1"
      status="planned"
      summary="Rank how much each kind of feature matters to you, then generate a personal map. The published map is never changed."
      onClose={onClose}
    >
      <PlannedControls>
        <ul className="weight-list">
          {CATEGORIES.map((category) => (
            <li key={category}>
              <span id={`weight-${category}`}>{category}</span>
              <Slider size="small" disabled defaultValue={3} min={0} max={5} step={1} aria-labelledby={`weight-${category}`} />
            </li>
          ))}
        </ul>
        <div className="panel-actions">
          <Button variant="contained" size="small" disabled disableElevation>Generate map</Button>
          <Button size="small" disabled>Back to default map</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
