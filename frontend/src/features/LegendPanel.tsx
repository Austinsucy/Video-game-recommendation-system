import type { MapGame } from '../services/gameService';
import FeaturePanel from './FeaturePanel';

interface LegendEntry { id: number; name: string; color: string; count: number; }

function clusterLegend(games: MapGame[]): LegendEntry[] {
  const entries = new Map<number, LegendEntry>();
  for (const game of games) {
    const entry = entries.get(game.clusterId);
    if (entry) entry.count += 1;
    else entries.set(game.clusterId, { id: game.clusterId, name: game.clusterName, color: game.clusterColor, count: 1 });
  }
  return [...entries.values()].sort((a, b) => a.id - b.id);
}

export default function LegendPanel({ games, onClose }: { games: MapGame[]; onClose: () => void }) {
  const entries = clusterLegend(games);
  return (
    <FeaturePanel
      title="Legend"
      requirement="CL 1"
      status="partial"
      summary="Each colour is a group of games with similar features. Cluster names summarize common features and are not official genres."
      onClose={onClose}
    >
      <ul className="legend-list">
        {entries.map((entry) => (
          <li key={entry.id}>
            <span className="cluster-swatch" style={{ backgroundColor: entry.color }} aria-hidden="true" />
            <span className="legend-name">{entry.name}</span>
            <span className="legend-count">{entry.count} games</span>
          </li>
        ))}
      </ul>
      <p className="planned-note">
        Descriptive cluster names are not available yet. Until the team approves them, each cluster is
        shown as "Cluster" and its number.
      </p>
    </FeaturePanel>
  );
}
