import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import { useState, type ReactNode, type Ref } from 'react';
import type { GameDetails, GameSummary, MapGame } from '../../services/gameService';
import { CloseIcon } from '../icons';

interface GameInfoPanelProps {
  /** Shown immediately from the map data (GIP 1). */
  game: MapGame;
  /** Null while loading or after an error. */
  details: GameDetails | null;
  error: string;
  onClose: () => void;
  onSelectSimilar: (game: GameSummary) => void;
  closeButtonRef?: Ref<HTMLButtonElement>;
}

function Unavailable() {
  return <span className="unavailable">Unavailable</span>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="info-field">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) return <Unavailable />;
  return (
    <ul className="chip-list">
      {items.map((item) => <li key={item}><Chip size="small" variant="outlined" label={item} /></li>)}
    </ul>
  );
}

function Cover({ url, title }: { url: string | null; title: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  if (!url || failedUrl === url) {
    return <div className="cover cover-placeholder">Cover image unavailable</div>;
  }
  return <img className="cover" src={url} alt={`${title} cover`} onError={() => setFailedUrl(url)} />;
}

/** GIP 1 game information panel. Fields the data does not have yet show "Unavailable". */
export default function GameInfoPanel({ game, details, error, onClose, onSelectSimilar, closeButtonRef }: GameInfoPanelProps) {
  const loading = !details && !error;
  return (
    <aside
      className="floating-panel info-panel"
      aria-labelledby="game-info-title"
      aria-busy={loading}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="panel-header">
        <div className="panel-heading">
          <div className="info-cluster">
            <span className="cluster-swatch" style={{ backgroundColor: game.clusterColor }} aria-hidden="true" />
            {game.clusterName}
          </div>
          <h2 id="game-info-title">{game.title}</h2>
        </div>
        <IconButton ref={closeButtonRef} size="small" aria-label="Close game information" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </header>
      {loading && <LinearProgress className="panel-progress" aria-label="Loading game information" />}

      <div className="panel-body">
        {error && <p className="panel-error" role="alert">{error}</p>}
        <Cover url={details?.coverUrl ?? null} title={game.title} />

        <dl className="info-fields">
          <Field label="Genres"><ChipList items={game.genres} /></Field>
          <Field label="Release year">{details?.releaseYear ?? <Unavailable />}</Field>
          <Field label="Platforms">{details?.platforms.length ? details.platforms.join(', ') : <Unavailable />}</Field>
          <Field label="Rating">{details?.rating ?? <Unavailable />}</Field>
          <Field label="Average playtime">
            {details?.averagePlaytimeHours != null ? `${details.averagePlaytimeHours} hours` : <Unavailable />}
          </Field>
          <Field label="Steam reviews">
            {game.popularity != null ? game.popularity.toLocaleString() : <Unavailable />}
          </Field>
          <Field label="Store page">
            {details?.storeUrl
              ? <Link href={details.storeUrl} target="_blank" rel="noopener noreferrer">Open store page</Link>
              : <Unavailable />}
          </Field>
        </dl>

        <section className="info-section" aria-labelledby="info-description">
          <h3 id="info-description">Description</h3>
          {details?.description ? <p>{details.description}</p> : <p><Unavailable /></p>}
        </section>

        <section className="info-section" aria-labelledby="info-tags">
          <h3 id="info-tags">Important tags</h3>
          <ChipList items={details?.tags ?? []} />
        </section>

        <section className="info-section" aria-labelledby="info-similar">
          <h3 id="info-similar">Similar games</h3>
          {details?.similarGames.length ? (
            <ol className="similar-list">
              {details.similarGames.map((similar) => (
                <li key={similar.id}>
                  <Link component="button" type="button" onClick={() => onSelectSimilar(similar)}>{similar.title}</Link>
                </li>
              ))}
            </ol>
          ) : <p><Unavailable /></p>}
        </section>
      </div>
    </aside>
  );
}
