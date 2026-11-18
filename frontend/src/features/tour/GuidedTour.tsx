import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeftIcon, ArrowRightIcon } from '../../components/icons';
import { STATUS_LABEL } from '../featureStatus';
import type { TourPlacement, TourStep } from './tourSteps';

interface GuidedTourProps {
  steps: TourStep[];
  /** Called when the user finishes or skips. `finished` is false for Skip and Esc. */
  onClose: (finished: boolean) => void;
}

const SPOT_PAD = 6; // space between the element and the highlight ring
const CARD_GAP = 12; // space between the highlight and the card
const EDGE = 12; // closest the card may sit to the window edge

interface Box { top: number; left: number; width: number; height: number }

function findTarget(selector?: string): Box | null {
  if (!selector) return null;
  const element = document.querySelector(selector);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null; // hidden
  return {
    top: rect.top - SPOT_PAD,
    left: rect.left - SPOT_PAD,
    width: rect.width + 2 * SPOT_PAD,
    height: rect.height + 2 * SPOT_PAD,
  };
}

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, Math.max(min, max)));

/** Works out where the card goes so it stays on screen and off the highlight. */
function placeCard(spot: Box | null, placement: TourPlacement, card: { width: number; height: number }) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const centred = { top: (vh - card.height) / 2, left: (vw - card.width) / 2 };
  if (!spot || placement === 'center') return centred;

  const below = spot.top + spot.height + CARD_GAP;
  const above = spot.top - CARD_GAP - card.height;
  const midLeft = spot.left + spot.width / 2 - card.width / 2;

  if (placement === 'left') {
    const left = spot.left - CARD_GAP - card.width;
    if (left >= EDGE) {
      return { top: clamp(spot.top + spot.height - card.height, EDGE, vh - card.height - EDGE), left };
    }
  }
  const fitsBelow = below + card.height <= vh - EDGE;
  const fitsAbove = above >= EDGE;
  const top = placement === 'top'
    ? (fitsAbove || !fitsBelow ? above : below)
    : (fitsBelow || !fitsAbove ? below : above);
  return {
    top: clamp(top, EDGE, vh - card.height - EDGE),
    left: clamp(midLeft, EDGE, vw - card.width - EDGE),
  };
}

/**
 * GW 1: a step-by-step tour that highlights parts of the page. Back and Next
 * (or the ← and → keys) move through it; Skip or Esc ends it at any step.
 * While it is open the rest of the page is inert, so focus stays in the card.
 */
export default function GuidedTour({ steps, onClose }: GuidedTourProps) {
  const [index, setIndex] = useState(0);
  const backdropRef = useRef<HTMLDivElement>(null);
  const spotRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  const step = steps[index];
  const isFirst = index === 0;
  const isLast = index === steps.length - 1;

  const goBack = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);
  const goNext = useCallback(() => {
    if (isLast) onClose(true);
    else setIndex((i) => i + 1);
  }, [isLast, onClose]);
  const skip = useCallback(() => onClose(false), [onClose]);

  // Position the highlight and the card before the browser paints, and again
  // when the window changes size. This writes styles straight to the DOM
  // because it depends on measuring elements outside React.
  useLayoutEffect(() => {
    function position() {
      const backdrop = backdropRef.current;
      const spotEl = spotRef.current;
      const card = cardRef.current;
      if (!backdrop || !spotEl || !card) return;
      const spot = findTarget(step.target);
      backdrop.classList.toggle('is-dimmed', !spot); // no highlight: dim the whole page instead
      spotEl.hidden = !spot;
      if (spot) {
        Object.assign(spotEl.style, {
          top: `${spot.top}px`, left: `${spot.left}px`, width: `${spot.width}px`, height: `${spot.height}px`,
        });
      }
      const { top, left } = placeCard(spot, step.placement ?? 'bottom', { width: card.offsetWidth, height: card.offsetHeight });
      Object.assign(card.style, { top: `${top}px`, left: `${left}px`, visibility: 'visible' });
    }
    position();
    window.addEventListener('resize', position);
    return () => window.removeEventListener('resize', position);
  }, [step]);

  // Make the app inert while the tour is open, and put focus back afterwards.
  // This must run before the effect below moves focus into the card.
  useEffect(() => {
    const root = document.getElementById('root');
    const previous = document.activeElement as HTMLElement | null;
    if (root) root.inert = true;
    return () => {
      if (root) root.inert = false;
      previous?.focus?.();
    };
  }, []);

  // Keep keyboard focus on the main action as the user moves through.
  useEffect(() => {
    nextRef.current?.focus();
  }, [index]);

  // ← / → move, Esc skips. Captured so the map's own arrow keys do not pan it.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'ArrowRight') goNext();
      else if (event.key === 'ArrowLeft') goBack();
      else if (event.key === 'Escape') skip();
      else return;
      event.preventDefault();
      event.stopPropagation();
    }
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [goNext, goBack, skip]);

  return createPortal(
    <div className="tour-layer">
      {/* Blocks clicks on the page. With no target, it also dims the page. */}
      <div ref={backdropRef} className="tour-backdrop" />
      <div ref={spotRef} className="tour-spotlight" aria-hidden="true" hidden />

      {/* Hidden until the first layout pass places it, so it does not jump. */}
      <div
        ref={cardRef}
        className="tour-card"
        style={{ visibility: 'hidden' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
      >
        <div className="tour-meta">
          <span className="tour-count" aria-live="polite">
            Step {index + 1} of {steps.length}
          </span>
          {step.status && (
            <Chip
              size="small"
              variant="outlined"
              label={STATUS_LABEL[step.status]}
              className={`status-chip status-${step.status}`}
            />
          )}
        </div>
        <h2 id="tour-title" className="tour-title">{step.title}</h2>
        <p id="tour-body" className="tour-body">{step.body}</p>

        <div className="tour-dots" aria-hidden="true">
          {steps.map((s, i) => (
            <span key={s.title} className={i === index ? 'is-current' : i < index ? 'is-done' : ''} />
          ))}
        </div>

        <div className="tour-actions">
          <Button size="small" color="inherit" className="tour-skip" onClick={skip}>
            {isLast ? 'Close' : 'Skip tour'}
          </Button>
          <div className="tour-nav">
            <Tooltip title="Back (←)">
              <span>
                <IconButton size="small" aria-label="Previous step" disabled={isFirst} onClick={goBack}>
                  <ArrowLeftIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Button
              ref={nextRef}
              size="small"
              variant="contained"
              disableElevation
              aria-label={isLast ? 'Finish tour' : 'Next step'}
              endIcon={isLast ? undefined : <ArrowRightIcon fontSize="small" />}
              onClick={goNext}
            >
              {isLast ? 'Finish' : 'Next'}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
