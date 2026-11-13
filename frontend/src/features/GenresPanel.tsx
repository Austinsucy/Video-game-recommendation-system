import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import FeaturePanel from './FeaturePanel';

interface GenresPanelProps {
  genres: string[];
  selectedGenre: string;
  onGenreChange: (genre: string) => void;
  onClose: () => void;
}

export default function GenresPanel({ genres, selectedGenre, onGenreChange, onClose }: GenresPanelProps) {
  return (
    <FeaturePanel
      title="Genres"
      requirement="GV 1"
      status="available"
      summary="Choose one genre to fade the other games. Games keep their positions on the map."
      onClose={onClose}
    >
      <TextField
        id="genre-filter"
        select
        size="small"
        fullWidth
        label="Genre"
        value={selectedGenre}
        onChange={(event) => onGenreChange(event.target.value)}
        helperText={selectedGenre ? `${selectedGenre} games are highlighted.` : 'All games are highlighted.'}
      >
        <MenuItem value="">All genres</MenuItem>
        {genres.map((genre) => <MenuItem key={genre} value={genre}>{genre}</MenuItem>)}
      </TextField>
      <div className="panel-actions">
        <Button size="small" disabled={selectedGenre === ''} onClick={() => onGenreChange('')}>
          Clear filter
        </Button>
      </div>
    </FeaturePanel>
  );
}
