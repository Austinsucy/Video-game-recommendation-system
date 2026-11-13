import type { MapGame } from '../services/gameService';
import type { FeatureId } from './features';
import GenresPanel from './GenresPanel';
import HelpPanel from './HelpPanel';
import LegendPanel from './LegendPanel';
import RecommendationsPanel from './RecommendationsPanel';
import SaveSharePanel from './SaveSharePanel';
import ScanPanel from './ScanPanel';
import SteamLibraryPanel from './SteamLibraryPanel';
import type { ScanState } from './useScan';

interface FeaturePanelHostProps {
  feature: FeatureId;
  games: MapGame[];
  /** Every genre in the map, sorted. */
  genres: string[];
  scan: ScanState;
  onClose: () => void;
}

/** Renders the panel for the toolbar feature that is open. */
export default function FeaturePanelHost({ feature, games, genres, scan, onClose }: FeaturePanelHostProps) {
  switch (feature) {
    case 'recommendations':
      return <RecommendationsPanel onClose={onClose} />;
    case 'genres':
      return <GenresPanel genres={genres} onClose={onClose} />;
    case 'legend':
      return <LegendPanel games={games} onClose={onClose} />;
    case 'scan':
      return <ScanPanel scan={scan} onClose={onClose} />;
    case 'share':
      return <SaveSharePanel onClose={onClose} />;
    case 'steam':
      return <SteamLibraryPanel onClose={onClose} />;
    case 'help':
      return <HelpPanel onClose={onClose} />;
  }
}
