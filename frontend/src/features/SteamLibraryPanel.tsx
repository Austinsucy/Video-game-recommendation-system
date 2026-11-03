import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

export default function SteamLibraryPanel({ onClose }: { onClose: () => void }) {
  return (
    <FeaturePanel
      title="Steam Library"
      requirement="SI 1"
      status="planned"
      summary="Enter a public Steam ID to show the games you own on the map and get recommendations from them. The site never asks for a password."
      onClose={onClose}
    >
      <PlannedControls>
        <TextField size="small" fullWidth disabled label="Steam ID" />
        <div className="panel-actions">
          <Button variant="contained" size="small" disabled disableElevation>Load library</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
