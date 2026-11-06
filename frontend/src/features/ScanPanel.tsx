import Button from '@mui/material/Button';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

export default function ScanPanel({ onClose }: { onClose: () => void }) {
  return (
    <FeaturePanel
      title="Scan"
      requirement="SC 1"
      status="planned"
      summary="Scan picks a random game every 5 seconds, centres the map on it and opens its information until you stop it. With a genre filter on, it only picks games in that genre."
      onClose={onClose}
    >
      <PlannedControls>
        <div className="panel-actions">
          <Button variant="contained" size="small" disabled disableElevation>Start scan</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
