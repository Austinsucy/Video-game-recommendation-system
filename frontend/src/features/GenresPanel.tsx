import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import FeaturePanel, { PlannedControls } from './FeaturePanel';

export default function GenresPanel({ genres, onClose }: { genres: string[]; onClose: () => void }) {
  return (
    <FeaturePanel
      title="Genres"
      requirement="GV 1"
      status="planned"
      summary="Choose one genre to fade out the other games. Games keep their positions on the map."
      onClose={onClose}
    >
      <PlannedControls note={`The genre list is real (${genres.length} genres in this map version), but filtering does nothing yet.`}>
        <TextField select size="small" fullWidth disabled label="Genre" value="">
          <MenuItem value="">All genres</MenuItem>
          {genres.map((genre) => <MenuItem key={genre} value={genre}>{genre}</MenuItem>)}
        </TextField>
        <div className="panel-actions">
          <Button size="small" disabled>Clear filter</Button>
        </div>
      </PlannedControls>
    </FeaturePanel>
  );
}
