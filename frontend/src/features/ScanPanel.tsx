import Button from '@mui/material/Button';
import FeaturePanel from './FeaturePanel';
import { SCAN_INTERVAL_MS, type ScanState } from './useScan';

interface ScanPanelProps {
  scan: ScanState;
  onClose: () => void;
}

export default function ScanPanel({ scan, onClose }: ScanPanelProps) {
  const seconds = SCAN_INTERVAL_MS / 1000;
  const count = scan.poolSize.toLocaleString();
  return (
    <FeaturePanel
      title="Scan"
      requirement="SC 1"
      status="partial"
      summary={`Scan picks a random game every ${seconds} seconds, centres the map on it and opens its information until you stop it. With a genre filter on, it only picks games in that genre. Choosing a game yourself, closing the game information or closing this panel also stops it.`}
      onClose={onClose}
    >
      <div className="scan-controls">
        <p className="scan-pool">
          {scan.genre ? `Picking from ${count} ${scan.genre} games` : `Picking from all ${count} games`}
        </p>

        <div className="panel-actions">
          {scan.running ? (
            <>
              <Button variant="contained" size="small" disableElevation onClick={scan.stop}>Stop scan</Button>
              <Button size="small" onClick={scan.skip}>Next game</Button>
            </>
          ) : (
            <Button
              variant="contained"
              size="small"
              disableElevation
              disabled={scan.poolSize === 0}
              onClick={scan.start}
            >
              Start scan
            </Button>
          )}
        </div>

        {scan.running && (
          <div className="scan-countdown" aria-hidden="true">
            <span key={scan.step} style={{ animationDuration: `${SCAN_INTERVAL_MS}ms` }} />
          </div>
        )}

        <p className="scan-status" role="status">
          {scan.running && scan.current && <>Showing <strong>{scan.current.title}</strong></>}
          {!scan.running && scan.current && <>Stopped on <strong>{scan.current.title}</strong></>}
        </p>
      </div>
      <p className="planned-note">
        The genre filter (GV 1) is not available yet, so Scan picks from every game for now.
      </p>
    </FeaturePanel>
  );
}
