import { useEffect, useImperativeHandle, useRef, type KeyboardEvent, type Ref } from 'react';
import cytoscape, { type Core } from 'cytoscape';
import type { MapGame } from '../../services/gameService';
import { placeLabels, type LabelCandidate } from './labelPlacement';
import { buildMapStyle, LABEL_FONT, LABEL_FONT_SIZE, LABEL_GAP, LABEL_MAX_WIDTH, NODE_SIZE } from './mapStyle';

/** Map actions other components can call (toolbar, search, future features). */
export interface GameMapHandle {
  zoomIn(): void;
  zoomOut(): void;
  /** Fit every game on screen. */
  resetView(): void;
  /**
   * Pan and zoom to a game, e.g. after a search (SB 1) or scan (SC 1).
   * `obscuredRight` is the width in px covered by a panel on the right;
   * the game is centred in the rest of the map.
   */
  focusGame(id: number, obscuredRight?: number): void;
  /** Move keyboard focus to the map. */
  focus(): void;
}

interface GameMapProps {
  games: MapGame[];
  selectedId: number | null;
  onSelectGame: (game: MapGame) => void;
  ref?: Ref<GameMapHandle>;
}

const FIT_PADDING = 40;
const MIN_ZOOM_FACTOR = 0.6; // relative to the fitted zoom
const MAX_ZOOM_FACTOR = 30;
const FOCUS_ZOOM_FACTOR = 5;
const ZOOM_STEP = 1.5;
const KEY_PAN_STEP = 80;
const PAN_MARGIN = 120; // px of the map that must stay on screen (bounded pan)
const SCREEN_AREA_PER_LABEL = 20000; // px²; limits label density
const LABEL_SETTLE_MS = 120;
const RESTYLE_TOLERANCE = 0.06; // ~6% zoom change
const STATUS_LINE_HEIGHT = 36; // keep labels clear of the .map-status line

interface MapController {
  cy: Core;
  fitZoom: number;
  updateLabels: () => void;
}

export default function GameMap({ games, selectedId, onSelectGame, ref }: GameMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<MapController | null>(null);
  const onSelectRef = useRef(onSelectGame);
  const selectedIdRef = useRef(selectedId);

  useEffect(() => {
    onSelectRef.current = onSelectGame;
  }, [onSelectGame]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const gamesById = new Map(games.map((game) => [String(game.id), game]));
    // Most popular first, so they win label space.
    const byPopularity = [...games].sort(
      (a, b) => (b.popularity ?? -1) - (a.popularity ?? -1) || a.id - b.id,
    );

    const cy = cytoscape({
      container,
      elements: games.map((game) => ({
        data: { id: String(game.id), title: game.title, color: game.clusterColor },
        position: { x: game.x, y: game.y },
      })),
      // Preset uses the stored positions instead of calculating new ones (REL 1).
      layout: { name: 'preset', fit: true, padding: FIT_PADDING },
      style: buildMapStyle(1),
      autoungrabify: true,
      autounselectify: true,
      boxSelectionEnabled: false,
    });

    const fitZoom = cy.zoom();
    cy.minZoom(fitZoom * MIN_ZOOM_FACTOR);
    cy.maxZoom(fitZoom * MAX_ZOOM_FACTOR);
    let styledZoom = fitZoom;
    cy.style(buildMapStyle(fitZoom));
    const bounds = cy.nodes().boundingBox();

    const measure = document.createElement('canvas').getContext('2d');
    const textWidths = new Map<string, number>();
    function textWidth(title: string) {
      let width = textWidths.get(title);
      if (width === undefined) {
        if (measure) measure.font = LABEL_FONT;
        width = Math.min(LABEL_MAX_WIDTH, measure ? measure.measureText(title).width : title.length * 7);
        textWidths.set(title, width);
      }
      return width;
    }

    function updateLabels() {
      const zoom = cy.zoom();
      const pan = cy.pan();
      const width = cy.width();
      const height = cy.height();
      const selected = gamesById.get(String(selectedIdRef.current));
      function* candidates(): Generator<LabelCandidate> {
        // The selected game's label is reserved first so others avoid it.
        if (selected) yield* onScreen([selected]);
        yield* onScreen(byPopularity.filter((game) => game !== selected));
      }
      function* onScreen(list: MapGame[]): Generator<LabelCandidate> {
        for (const game of list) {
          const x = game.x * zoom + pan.x;
          const y = game.y * zoom + pan.y;
          if (x < 0 || y < 0 || x > width || y > height) continue;
          yield { id: String(game.id), x, y, width: textWidth(game.title) };
        }
      }
      const ids = placeLabels(candidates(), {
        viewWidth: width,
        viewHeight: height - STATUS_LINE_HEIGHT,
        labelHeight: LABEL_FONT_SIZE + 4,
        offset: NODE_SIZE / 2 + LABEL_GAP,
        padding: 3,
        maxLabels: Math.max(8, Math.round((width * height) / SCREEN_AREA_PER_LABEL)),
      });
      cy.batch(() => {
        cy.nodes('.has-label').removeClass('has-label');
        for (const id of ids) cy.getElementById(id).addClass('has-label');
      });
    }

    // Keep at least PAN_MARGIN px of the map on screen (bounded pan, GM 2).
    function clampPan() {
      const zoom = cy.zoom();
      const pan = cy.pan();
      const width = cy.width();
      const height = cy.height();
      const marginX = Math.min(PAN_MARGIN, width / 2);
      const marginY = Math.min(PAN_MARGIN, height / 2);
      const left = bounds.x1 * zoom + pan.x;
      const right = bounds.x2 * zoom + pan.x;
      const top = bounds.y1 * zoom + pan.y;
      const bottom = bounds.y2 * zoom + pan.y;
      const dx = right < marginX ? marginX - right : left > width - marginX ? width - marginX - left : 0;
      const dy = bottom < marginY ? marginY - bottom : top > height - marginY ? height - marginY - top : 0;
      if (dx || dy) cy.panBy({ x: dx, y: dy });
    }

    let frame = 0;
    let settleTimer = 0;
    // Restyling all nodes takes ~10 ms, so while the user is zooming it only
    // happens after a noticeable change; the exact size is applied once the
    // view settles. This keeps pan and zoom smooth (PERF 3).
    function restyle(tolerance: number) {
      const zoom = cy.zoom();
      if (Math.abs(Math.log(zoom / styledZoom)) > tolerance) {
        styledZoom = zoom;
        cy.style(buildMapStyle(zoom));
      }
    }
    function onViewport() {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          clampPan();
          restyle(RESTYLE_TOLERANCE);
        });
      }
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        restyle(0);
        updateLabels();
      }, LABEL_SETTLE_MS);
    }
    cy.on('viewport', onViewport);

    cy.on('tap', 'node', (event) => {
      const game = gamesById.get(event.target.id());
      if (game) onSelectRef.current(game);
    });
    cy.on('mouseover', 'node', (event) => {
      event.target.addClass('is-hovered');
      container.style.cursor = 'pointer';
    });
    cy.on('mouseout', 'node', (event) => {
      event.target.removeClass('is-hovered');
      container.style.cursor = '';
    });

    controllerRef.current = { cy, fitZoom, updateLabels };
    updateLabels();

    const observer = new ResizeObserver(() => {
      cy.resize();
      onViewport();
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      controllerRef.current = null;
      cy.destroy();
    };
  }, [games]);

  // Selection only changes classes, so the viewport stays where the user left it.
  useEffect(() => {
    selectedIdRef.current = selectedId;
    const controller = controllerRef.current;
    if (!controller) return;
    const { cy } = controller;
    cy.batch(() => {
      cy.nodes('.is-selected').removeClass('is-selected');
      if (selectedId !== null) cy.getElementById(String(selectedId)).addClass('is-selected');
    });
    controller.updateLabels();
  }, [games, selectedId]);

  useImperativeHandle(ref, () => {
    function zoomTo(level: number, center: { x: number; y: number }, pan?: { x: number; y: number }) {
      const controller = controllerRef.current;
      if (!controller) return;
      const { cy } = controller;
      const zoom = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), level));
      const current = cy.pan();
      const scale = zoom / cy.zoom();
      cy.stop(true, false);
      cy.animate({
        zoom,
        pan: pan ?? { x: center.x - (center.x - current.x) * scale, y: center.y - (center.y - current.y) * scale },
        duration: 200,
        easing: 'ease-out-cubic',
      });
    }
    function viewCenter(cy: Core) {
      return { x: cy.width() / 2, y: cy.height() / 2 };
    }
    return {
      zoomIn() {
        const cy = controllerRef.current?.cy;
        if (cy) zoomTo(cy.zoom() * ZOOM_STEP, viewCenter(cy));
      },
      zoomOut() {
        const cy = controllerRef.current?.cy;
        if (cy) zoomTo(cy.zoom() / ZOOM_STEP, viewCenter(cy));
      },
      resetView() {
        const cy = controllerRef.current?.cy;
        if (!cy) return;
        cy.stop(true, false);
        cy.animate({ fit: { eles: cy.nodes(), padding: FIT_PADDING }, duration: 250, easing: 'ease-out-cubic' });
      },
      focusGame(id, obscuredRight = 0) {
        const controller = controllerRef.current;
        const node = controller?.cy.getElementById(String(id));
        if (!controller || !node || node.empty()) return;
        const { cy, fitZoom } = controller;
        const level = Math.min(cy.maxZoom(), Math.max(cy.zoom(), fitZoom * FOCUS_ZOOM_FACTOR));
        const position = node.position();
        const visibleWidth = Math.max(cy.width() - obscuredRight, cy.width() / 2);
        zoomTo(level, viewCenter(cy), {
          x: visibleWidth / 2 - position.x * level,
          y: cy.height() / 2 - position.y * level,
        });
      },
      focus() {
        containerRef.current?.focus();
      },
    };
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const cy = controllerRef.current?.cy;
    if (!cy || event.target !== event.currentTarget) return;
    const pans: Record<string, [number, number]> = {
      ArrowLeft: [KEY_PAN_STEP, 0],
      ArrowRight: [-KEY_PAN_STEP, 0],
      ArrowUp: [0, KEY_PAN_STEP],
      ArrowDown: [0, -KEY_PAN_STEP],
    };
    const step = pans[event.key];
    if (step) {
      cy.panBy({ x: step[0], y: step[1] });
    } else if (event.key === '+' || event.key === '=') {
      cy.zoom({ level: cy.zoom() * ZOOM_STEP, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else if (event.key === '-' || event.key === '_') {
      cy.zoom({ level: cy.zoom() / ZOOM_STEP, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else {
      return;
    }
    event.preventDefault();
  }

  return (
    <div
      ref={containerRef}
      className="game-map-canvas"
      tabIndex={0}
      role="region"
      aria-label="Game map"
      aria-describedby="map-instructions"
      onKeyDown={handleKeyDown}
    />
  );
}
