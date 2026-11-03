import Autocomplete from '@mui/material/Autocomplete';
import InputAdornment from '@mui/material/InputAdornment';
import TextField from '@mui/material/TextField';
import { useState } from 'react';
import type { MapGame } from '../../services/gameService';
import { SearchIcon } from '../icons';

interface SearchBoxProps {
  games: MapGame[] | null;
  onSelectGame: (game: MapGame) => void;
}

const MAX_RESULTS = 8;

// SB 1 entry point. For now this matches titles in the map data already in
// the browser (it replaces the old "Choose a game" list). SB 1 later moves the
// lookup to FastAPI GET /games?search= with debouncing; keep onSelectGame as
// the single selection path.
export default function SearchBox({ games, onSelectGame }: SearchBoxProps) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const trimmed = query.trim();

  return (
    <Autocomplete<MapGame>
      className="search-box"
      size="small"
      options={games ?? []}
      disabled={!games?.length}
      value={null}
      inputValue={query}
      onInputChange={(_, value) => setQuery(value)}
      onChange={(_, game) => {
        if (game) onSelectGame(game);
      }}
      getOptionLabel={(game) => game.title}
      getOptionKey={(game) => game.id}
      filterOptions={(options) => {
        const needle = trimmed.toLowerCase();
        if (!needle) return [];
        return options.filter((game) => game.title.toLowerCase().includes(needle)).slice(0, MAX_RESULTS);
      }}
      // A blank query shows nothing rather than every game (SB 1).
      open={open && trimmed.length > 0}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      noOptionsText={`No games match "${trimmed}".`}
      autoHighlight
      clearOnBlur={false}
      forcePopupIcon={false}
      renderInput={(params) => (
        <TextField
          {...params}
          placeholder="Search games"
          slotProps={{
            ...params.slotProps,
            htmlInput: { ...params.slotProps.htmlInput, 'aria-label': 'Search games by title', maxLength: 100 },
            input: {
              ...params.slotProps.input,
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      )}
    />
  );
}
