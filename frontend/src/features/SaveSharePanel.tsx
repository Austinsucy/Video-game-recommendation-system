import Button from '@mui/material/Button';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

export default function SaveSharePanel({ onClose }: { onClose: () => void }) {
  return (
    <FeaturePanel
      title="Save / Share"
      requirement="MCS 1"
      status="planned"
      summary="Save the selected game, genre filter and recommendation settings in this browser, or copy a link that restores them. No account is needed."
      onClose={onClose}
    >
      <PlannedControls note="Nothing is saved in your browser yet. These controls do nothing.">
        <div className="panel-actions panel-actions-stacked">
          <Button variant="outlined" size="small" disabled>Save in this browser</Button>
          <Button variant="outlined" size="small" disabled>Copy share link</Button>
          <Button variant="outlined" size="small" disabled>Export settings</Button>
          <Button size="small" disabled>Reset saved data</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
