import { useCallback, useEffect, useRef, useState } from 'react';
import GameMap from '../src/components/gameMap';
import { getGameDetails, getMapGames } from './services/gameService';
import type { GameDetails, MapGame } from './services/gameService';
import './shell.css';

export default function App() {
  const [games, setGames] = useState<MapGame[] | null>(null);
  const [mapError, setMapError] = useState('');
  const [selectedGame, setSelectedGame] = useState<MapGame | null>(null);
  const [details, setDetails] = useState<GameDetails | null>(null);
  const [detailsError, setDetailsError] = useState<{ id: number; message: string } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const gameChooser = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    let ignore = false;
    getMapGames()
      .then((data) => { if (!ignore) setGames(data); })
      .catch(() => {
        if (!ignore) setMapError('The map could not load. Check data/map.db, then refresh to retry.');
      });
    return () => { ignore = true; };
  }, []);

  useEffect(() => {
    if (!selectedGame) return;
    let ignore = false;
    closeButton.current?.focus();
    getGameDetails(selectedGame.id)
      .then((data) => {
        if (!ignore) {
          setDetails(data);
          setDetailsError(null);
        }
      })
      .catch(() => {
        if (!ignore) setDetailsError({ id: selectedGame.id, message: 'Game information could not load.' });
      });
    return () => { ignore = true; };
  }, [selectedGame]);

  const selectGame = useCallback((game: MapGame) => {
    setSelectedGame(game);
  }, []);

  function closePanel() {
    setSelectedGame(null);
    setDetails(null);
    setDetailsError(null);
    gameChooser.current?.focus();
  }

  const visibleDetails = selectedGame && details?.id === selectedGame.id ? details : null;
  const visibleError = selectedGame && detailsError?.id === selectedGame.id ? detailsError.message : '';

  return (
    <div className="app-shell">
      <header className="site-header">
        <h1>A Gooner's Interactive Game Map</h1>
      </header>

      <main className="workspace">
        <section className="map-area" aria-label="Game map">
          {games && games.length > 0 && (
            <GameMap games={games} selectedId={selectedGame?.id ?? null} onSelectGame={selectGame} />
          )}
          {mapError && <p className="map-message" role="alert">{mapError}</p>}
          {!mapError && games === null && <p className="map-message" role="status">Loading map...</p>}
          {games?.length === 0 && <p className="map-message">No games are available.</p>}
          {games && games.length > 0 && (
            <p className="map-status">{games.length.toLocaleString()} games · Drag to pan · Scroll to zoom · Click a node</p>
          )}
        </section>

        <nav className="toolbar" aria-label="Game discovery controls">
          <input aria-label="Search games (coming later)" placeholder="Search games..." disabled />
          <select aria-label="Genre filter (coming later)" disabled><option>All genres</option></select>
          <button disabled>Scan</button>
          <label htmlFor="game-chooser">Choose a game</label>
          <select
            ref={gameChooser}
            id="game-chooser"
            disabled={!games?.length}
            value={selectedGame?.id ?? ''}
            onChange={(event) => {
              const game = games?.find((record) => record.id === Number(event.target.value));
              if (game) selectGame(game);
            }}
          >
            <option value="" disabled>Select a game...</option>
            {games?.map((game) => <option key={game.id} value={game.id}>{game.title}</option>)}
          </select>
          <p className="toolbar-note">The list also lets you select nodes with a keyboard.</p>
        </nav>

        {selectedGame && (
          <aside
            className="information-panel"
            aria-labelledby="game-title"
            onKeyDown={(event) => { if (event.key === 'Escape') closePanel(); }}
          >
            <button ref={closeButton} className="close-panel" onClick={closePanel} aria-label="Close game information">×</button>
            <h2 id="game-title">{selectedGame.title}</h2>
            {visibleError && <p role="alert">{visibleError}</p>}
            {!visibleDetails && !visibleError && <p role="status">Loading game details...</p>}
            {visibleDetails && (
              <>
                <p><strong>Genres:</strong> {visibleDetails.genres.join(', ') || 'Unavailable'}</p>
                <p className="cluster-label">
                  <span className="cluster-swatch" style={{ backgroundColor: visibleDetails.clusterColor }} />
                  <strong>Cluster:</strong> {visibleDetails.clusterName}
                </p>
                {visibleDetails.coverUrl ? (
                  <img className="game-cover" src={visibleDetails.coverUrl} alt={`${visibleDetails.title} cover`} />
                ) : (
                  <div className="cover-placeholder">Cover image unavailable</div>
                )}
                <p><strong>Release year:</strong> {visibleDetails.releaseYear ?? 'Unavailable'}</p>
                <p><strong>Players:</strong> {visibleDetails.players ?? 'Unavailable'}</p>
                <p><strong>Description:</strong> {visibleDetails.description ?? 'Unavailable'}</p>
              </>
            )}
          </aside>
        )}
      </main>
    </div>
  );
}
