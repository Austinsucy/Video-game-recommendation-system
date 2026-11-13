import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import { useEffect, useRef, type ReactNode } from 'react';
import { CloseIcon } from '../components/icons';

export type FeatureStatus = 'planned' | 'partial' | 'available';

interface FeaturePanelProps {
  title: string;
  /** Requirement id from the System Requirements document, e.g. "SC 1". */
  requirement: string;
  status: FeatureStatus;
  summary: string;
  onClose: () => void;
  children?: ReactNode;
}

const STATUS_LABEL: Record<FeatureStatus, string> = {
  planned: 'Not available yet',
  partial: 'Partly available',
  available: 'Available',
};

/** Shared frame for the toolbar feature panels. */
export default function FeaturePanel({ title, requirement, status, summary, onClose, children }: FeaturePanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [title]);

  return (
    <section
      id="feature-panel"
      className="floating-panel feature-panel"
      aria-labelledby="feature-panel-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="panel-header">
        <div className="panel-heading">
          <h2 id="feature-panel-title" ref={headingRef} tabIndex={-1}>{title}</h2>
          <div className="panel-meta">
            <span className="requirement-id">{requirement}</span>
            <Chip
              size="small"
              variant="outlined"
              label={STATUS_LABEL[status]}
              className={`status-chip status-${status}`}
            />
          </div>
        </div>
        <IconButton size="small" aria-label={`Close ${title}`} onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </header>
      <div className="panel-body">
        <p className="panel-summary">{summary}</p>
        {children}
      </div>
    </section>
  );
}

/** Wraps disabled controls that show where a future feature will go. */
export function PlannedControls({ children, note }: { children: ReactNode; note?: string }) {
  return (
    <div className="planned-controls">
      <p className="planned-note">{note ?? 'These controls are placeholders and do nothing yet.'}</p>
      {children}
    </div>
  );
}
