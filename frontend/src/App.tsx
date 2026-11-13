import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import GameInfoPanel from './components/info/GameInfoPanel';
import GameMap, { type GameMapHandle } from './components/map/GameMap';
import MapControls from './components/map/MapControls';
import TopToolbar from './components/toolbar/TopToolbar';
import FeaturePanelHost from './features/FeaturePanelHost';
import { featureButtonId, type FeatureId } from './features/features';
import { useScan } from './features/useScan';
import { getGameDetails, getMap } from './services/gameService';
import type { GameDetails, GameSummary, MapData, MapGame } from './services/gameService';
import type { ThemeMode } from './theme';
import './app.css';

// .info-panel width plus its margins in app.css. focusGame centres games in
// the part of the map the panel does not cover.
const INFO_PANEL_SPACE = 384;

interface AppProps {
  themeMode: ThemeMode;
  onToggleThemeMode: () => void;
}

export default function App({ themeMode, onToggleThemeMode }: AppProps) {
  const [map, setMap] = useState<MapData | null>(null);
  const [mapError, setMapError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [selectedGame, setSelectedGame] = useState<MapGame | null>(null);
  const [details, setDetails] = useState<GameDetails | null>(null);
  const [detailsError, setDetailsError] = useState<{ id: number; message: string } | null>(null);
  const [activeFeature, setActiveFeature] = useState<FeatureId | null>(null);
  // GV 1: the genre filter. Nothing sets it until the Genres panel works;
  // Scan (SC 1) already follows it.
  const [genreFilter] = useState<string | null>(null);
  const mapRef = useRef<GameMapHandle>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const infoPanelOpen = selectedGame !== null;

  // GM 2: load the map once; a failed load shows no nodes and a retry button (REL 3).
  useEffect(() => {
    let ignore = false;
    getMap()
      .then((data) => { if (!ignore) setMap(data); })
      .catch(() => {
        if (!ignore) setMapError('The game map could not be loaded. Check your connection, then try again.');
      });
    return () => { ignore = true; };
  }, [loadAttempt]);

  // GIP 1: the title shows at once; the rest fills in when the details arrive.
  // A late response for a previously selected game is ignored.
  useEffect(() => {
    if (!selectedGame) return;
    let ignore = false;
    getGameDetails(selectedGame.id)
      .then((data) => {
        if (!ignore) {
          setDetails(data);
          setDetailsError(null);
        }
      })
      .catch(() => {
        if (!ignore) {
          setDetailsError({
            id: selectedGame.id,
            message: 'This game\'s information could not be loaded. Select the game again to retry.',
          });
        }
      });
    return () => { ignore = true; };
  }, [selectedGame]);

  // Move focus into the panel when it opens, not every time the game changes.
  useEffect(() => {
    if (infoPanelOpen) closeButton.current?.focus();
  }, [infoPanelOpen]);

  // Every way of choosing a game (node click, search, similar games, scan)
  // goes through here. A node click leaves the viewport alone.
  const selectGame = useCallback((game: MapGame) => {
    setSelectedGame(game);
  }, []);

  function selectAndLocate(game: MapGame) {
    selectGame(game);
    mapRef.current?.focusGame(game.id, INFO_PANEL_SPACE);
  }

  // SC 1: scan picks go through selectAndLocate. Choosing a game yourself,
  // closing the info panel or closing the Scan panel stops the scan.
  const scan = useScan(map?.games ?? null, genreFilter, selectAndLocate);

  function chooseGame(game: MapGame) {
    scan.stop();
    selectGame(game);
  }

  function chooseAndLocate(game: MapGame) {
    scan.stop();
    selectAndLocate(game);
  }

  function selectSimilar(summary: GameSummary) {
    const game = map?.games.find((record) => record.id === summary.id);
    if (game) chooseAndLocate(game);
  }

  function closeInfoPanel() {
    scan.stop();
    setSelectedGame(null);
    setDetails(null);
    setDetailsError(null);
    mapRef.current?.focus();
  }

  function toggleFeature(id: FeatureId) {
    if (activeFeature === 'scan') scan.stop();
    setActiveFeature((current) => (current === id ? null : id));
  }

  function closeFeature() {
    if (activeFeature === 'scan') scan.stop();
    if (activeFeature) document.getElementById(featureButtonId(activeFeature))?.focus();
    setActiveFeature(null);
  }

  function retryMap() {
    setMapError('');
    setLoadAttempt((attempt) => attempt + 1);
  }

  const games = map?.games ?? null;
  const genres = useMemo(
    () => [...new Set((map?.games ?? []).flatMap((game) => game.genres))].sort(),
    [map],
  );
  const visibleDetails = selectedGame && details?.id === selectedGame.id ? details : null;
  const visibleError = selectedGame && detailsError?.id === selectedGame.id ? detailsError.message : '';

  return (
    <div className={`app-shell${infoPanelOpen ? ' has-info-panel' : ''}`}>
      <TopToolbar
        games={games}
        activeFeature={activeFeature}
        onToggleFeature={toggleFeature}
        onSearchSelect={chooseAndLocate}
        themeMode={themeMode}
        onToggleThemeMode={onToggleThemeMode}
      />

      <main
        className="map-area"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && infoPanelOpen) closeInfoPanel();
        }}
      >
        {games && games.length > 0 && (
          <GameMap
            ref={mapRef}
            games={games}
            selectedId={selectedGame?.id ?? null}
            onSelectGame={chooseGame}
            themeMode={themeMode}
          />
        )}

        {!map && !mapError && (
          <div className="map-message" role="status">
            <CircularProgress size={18} thickness={5} aria-hidden="true" />
            Loading map…
          </div>
        )}
        {mapError && (
          <div className="map-message map-error" role="alert">
            <p>{mapError}</p>
            <Button variant="outlined" size="small" onClick={retryMap}>Try again</Button>
          </div>
        )}
        {games?.length === 0 && (
          <div className="map-message" role="status">This map version has no games to show.</div>
        )}

        {map && games && games.length > 0 && (
          <>
            <p id="map-instructions" className="map-status">
              {games.length.toLocaleString()} games · map {map.version}
              <span className="map-hint"> · Drag to pan, scroll to zoom, click a dot for details</span>
            </p>
            <MapControls
              onZoomIn={() => mapRef.current?.zoomIn()}
              onZoomOut={() => mapRef.current?.zoomOut()}
              onReset={() => mapRef.current?.resetView()}
            />
          </>
        )}

        {activeFeature && (
          <FeaturePanelHost
            feature={activeFeature}
            games={games ?? []}
            genres={genres}
            scan={scan}
            onClose={closeFeature}
          />
        )}

        {selectedGame && (
          <GameInfoPanel
            game={selectedGame}
            details={visibleDetails}
            error={visibleError}
            onClose={closeInfoPanel}
            onSelectSimilar={selectSimilar}
            closeButtonRef={closeButton}
          />
        )}
      </main>
    </div>
  );
}
