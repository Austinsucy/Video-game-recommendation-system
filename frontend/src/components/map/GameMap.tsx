import { useEffect, useImperativeHandle, useRef, type Ref } from 'react';
import type { GameSummary, MapGame } from '../../services/gameService';
import type { ThemeMode } from '../../theme';
import { createDotLayer, drawDots2d, type DotData, type DotView } from './dotLayer';
import { baseRadius, dotScale, labelSize, PointGrid, popularityScores } from './mapScale';

// The map draws its own dots (WebGL, see dotLayer.ts) and labels (Canvas 2D)
// instead of using Cytoscape. Cytoscape walks every node in JavaScript on each
// frame, which held 72,746 games to about 1–5 fps; see docs/decisions.md.
// The look follows the Tag Vector Lab: dot and label size by Steam reviews,
// translucent dots, and labels only for the most reviewed games on screen.

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
  /**
   * The selected game's similar games, once they have loaded. The map draws a
   * line to each one and moves to show them all.
   */
  similarGames: GameSummary[] | undefined;
  /** Width in px covered by a panel on the right; the map frames a web in the rest. */
  obscuredRight: number;
  onSelectGame: (game: MapGame) => void;
  /** A click on empty map, as opposed to a drag. */
  onClickBackground: () => void;
  /** Redraws the labels and highlights in the new theme's colours. */
  themeMode: ThemeMode;
  ref?: Ref<GameMapHandle>;
}

const FIT_PADDING = 40;
const MIN_ZOOM_FACTOR = 0.6; // relative to the fitted zoom
const MAX_ZOOM_FACTOR = 30;
const FOCUS_ZOOM_FACTOR = 5;
const WEB_PADDING = 90;
const WEB_GROW_MS = 420; // each line's growth
const WEB_STAGGER_MS = 22; // delay between one line starting and the next
const WEB_FADE_MS = 150;
const GLIDE_MS = 900; // the slower camera move to a game or its web
const ZOOM_STEP = 1.5; // per +/− key press or button click
// Wheel zoom per pixel of scroll. Trackpad pinches arrive as Ctrl+wheel
// events with much smaller deltas, so they get a faster rate.
const WHEEL_ZOOM_RATE = 0.0015;
const PINCH_ZOOM_RATE = 0.012;
const WHEEL_LINE_ZOOM_RATE = 0.05; // wheels that scroll by lines, not pixels
const KEY_PAN_STEP = 80;
const PAN_MARGIN = 120; // px of the map that must stay on screen (bounded pan)
const ANIMATION_MS = 200;
const CLICK_SLOP = 5; // px a press may move and still count as a click
const HIT_SLOP = 2; // px around a dot that still counts as on it
const MIN_HIT_RADIUS = 4;
const LABELS_OVERVIEW = 25; // most reviewed games labelled at the fitted zoom
const LABELS_ZOOMED = 40;
const STATUS_LINE_HEIGHT = 36; // keep labels clear of the .map-status line

const FONT_FAMILY = '"Inter", "Segoe UI", system-ui, sans-serif';

// Canvas colours come from the --map-* CSS variables in app.css, so they
// follow light and dark mode.
interface MapPalette {
  text: string;
  muted: string;
  halo: string;
  selected: string;
  selectedUnderlay: string;
  tipBackground: string;
  tipBorder: string;
}

function readPalette(element: Element): MapPalette {
  const style = getComputedStyle(element);
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    text: read('--map-text', '#1f2937'),
    muted: read('--map-muted', '#4b5563'),
    halo: read('--map-halo', '#f7f7f5'),
    selected: read('--map-selected', '#111827'),
    selectedUnderlay: read('--map-selected-underlay', 'rgb(29 78 216 / 16%)'),
    tipBackground: read('--map-tip-bg', '#ffffff'),
    tipBorder: read('--map-tip-border', '#d4d4cf'),
  };
}

interface View {
  zoom: number;
  panX: number;
  panY: number;
}

interface MapController {
  zoomAround(factor: number, x: number, y: number, animate: boolean): void;
  /** Zoom toward the mouse when it is over the map, else the centre. */
  zoomAtPointer(factor: number): void;
  fit(): void;
  focusGame(id: number, obscuredRight: number): void;
  setWeb(selectedId: number | null, similarGames: GameSummary[] | undefined, obscuredRight: number): void;
  render(): void;
}

type Box = [left: number, top: number, right: number, bottom: number];

const easeOut = (t: number) => 1 - (1 - t) ** 3;
const easeInOut = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);

/** The lines from one game to its similar games, as draw indices. */
interface Web {
  source: number;
  targets: number[];
  startedAt: number;
  fadingSince: number | null;
}

function overlaps(box: Box, placed: Box[]) {
  return placed.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1]);
}

function hexToRgb(hex: string): [number, number, number] {
  const value = parseInt(hex.slice(1), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}

export default function GameMap({ games, selectedId, similarGames, obscuredRight, onSelectGame, onClickBackground, themeMode, ref }: GameMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dotCanvasRef = useRef<HTMLCanvasElement>(null);
  const labelCanvasRef = useRef<HTMLCanvasElement>(null);
  const controllerRef = useRef<MapController | null>(null);
  const onSelectRef = useRef(onSelectGame);
  const onClickBackgroundRef = useRef(onClickBackground);
  const selectedIdRef = useRef(selectedId);
  const paletteRef = useRef<MapPalette | null>(null);

  useEffect(() => {
    onSelectRef.current = onSelectGame;
    onClickBackgroundRef.current = onClickBackground;
  }, [onSelectGame, onClickBackground]);

  useEffect(() => {
    const container = containerRef.current;
    const dotCanvas = dotCanvasRef.current;
    const labelCanvas = labelCanvasRef.current;
    const context = labelCanvas?.getContext('2d');
    if (!container || !dotCanvas || !labelCanvas || !context) return;
    paletteRef.current ??= readPalette(container);

    // ---- Data, in draw order: least reviewed first, so popular dots sit on top.
    const n = games.length;
    const scores = popularityScores(games);
    const order = Array.from({ length: n }, (_, i) => i)
      .sort((a, b) => scores[a] - scores[b] || games[b].id - games[a].id);
    const data: DotData = {
      xs: new Float32Array(n),
      ys: new Float32Array(n),
      scales: new Float32Array(n),
      colors: new Float32Array(n * 3),
    };
    const popularity = new Float32Array(n);
    const hexColors: string[] = [];
    const drawIndexById = new Map<number, number>();
    order.forEach((g, d) => {
      const game = games[g];
      data.xs[d] = game.x;
      data.ys[d] = game.y;
      popularity[d] = scores[g];
      data.scales[d] = dotScale(scores[g], n);
      data.colors.set(hexToRgb(game.clusterColor), d * 3);
      hexColors.push(game.clusterColor);
      drawIndexById.set(game.id, d);
    });
    const gameAt = (d: number) => games[order[d]];
    const maxScale = dotScale(1, n);
    const grid = new PointGrid(data.xs, data.ys);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (let d = 0; d < n; d++) {
      minX = Math.min(minX, data.xs[d]); maxX = Math.max(maxX, data.xs[d]);
      minY = Math.min(minY, data.ys[d]); maxY = Math.max(maxY, data.ys[d]);
    }

    const dots = createDotLayer(dotCanvas, data); // null: draw dots in 2D instead

    // ---- View state
    let width = 0;
    let height = 0;
    let dpr = 1;
    let fitZoom = 1;
    let view: View = { zoom: 1, panX: 0, panY: 0 };
    let fitted = false;
    let hovered = -1;
    let frame = 0;
    let animation = 0;
    let web: Web | null = null;
    // Counts the user's own pans and zooms, so a web that arrives after one
    // does not move the view out from under them (GM 2).
    let userMoves = 0;
    let movesAtSelection = 0;
    let trackedSelection: number | null = null;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function clampZoom(zoom: number) {
      return Math.min(fitZoom * MAX_ZOOM_FACTOR, Math.max(fitZoom * MIN_ZOOM_FACTOR, zoom));
    }

    function visibleWidth(obscuredRight: number) {
      return Math.max(width - obscuredRight, width / 2);
    }

    // The view that fits a box of map coordinates into the left
    // `availableWidth` px. `limitZoom` runs before the pan is worked out, so a
    // limited zoom still centres the box.
    function viewForBox(
      left: number, top: number, right: number, bottom: number,
      availableWidth: number, padding: number, limitZoom = (zoom: number) => zoom,
    ): View {
      const zoom = limitZoom(Math.max(
        Math.min(
          (availableWidth - 2 * padding) / Math.max(right - left, 1e-6),
          (height - 2 * padding) / Math.max(bottom - top, 1e-6),
        ),
        1e-6,
      ));
      return {
        zoom,
        panX: availableWidth / 2 - ((left + right) / 2) * zoom,
        panY: height / 2 - ((top + bottom) / 2) * zoom,
      };
    }

    function fitView(): View {
      return viewForBox(minX, minY, maxX, maxY, width, FIT_PADDING);
    }

    // Zoom limits, and at least PAN_MARGIN px of the map on screen (bounded pan, GM 2).
    function clamp(next: View): View {
      const zoom = clampZoom(next.zoom);
      const scale = zoom / next.zoom;
      let { panX, panY } = next;
      if (scale !== 1) {
        panX = width / 2 - (width / 2 - panX) * scale;
        panY = height / 2 - (height / 2 - panY) * scale;
      }
      const marginX = Math.min(PAN_MARGIN, width / 2);
      const marginY = Math.min(PAN_MARGIN, height / 2);
      const left = minX * zoom + panX, right = maxX * zoom + panX;
      const top = minY * zoom + panY, bottom = maxY * zoom + panY;
      if (right < marginX) panX += marginX - right;
      else if (left > width - marginX) panX += width - marginX - left;
      if (bottom < marginY) panY += marginY - bottom;
      else if (top > height - marginY) panY += height - marginY - top;
      return { zoom, panX, panY };
    }

    function setView(next: View) {
      view = clamp(next);
      render();
    }

    function stopAnimation() {
      cancelAnimationFrame(animation);
      animation = 0;
    }

    function takeControl() {
      userMoves++;
      stopAnimation();
    }

    // The zoom changes by an equal ratio each step and the map point at the
    // screen centre travels in a straight line, so a large zoom change reads
    // as one steady move.
    function animateTo(target: View, duration = ANIMATION_MS, ease = easeOut) {
      stopAnimation();
      const to = clamp(target);
      if (reducedMotion.matches) {
        setView(to);
        return;
      }
      const from = view;
      const centreX = (v: View) => (width / 2 - v.panX) / v.zoom;
      const centreY = (v: View) => (height / 2 - v.panY) / v.zoom;
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        const e = ease(t);
        const zoom = from.zoom * (to.zoom / from.zoom) ** e;
        view = {
          zoom,
          panX: width / 2 - (centreX(from) + (centreX(to) - centreX(from)) * e) * zoom,
          panY: height / 2 - (centreY(from) + (centreY(to) - centreY(from)) * e) * zoom,
        };
        // Set before drawing: drawWeb reads it to know whether this loop will draw the next frame.
        animation = t < 1 ? requestAnimationFrame(step) : 0;
        draw();
      };
      animation = requestAnimationFrame(step);
    }

    function zoomedView(factor: number, x: number, y: number): View {
      const zoom = clampZoom(view.zoom * factor);
      const scale = zoom / view.zoom;
      return { zoom, panX: x - (x - view.panX) * scale, panY: y - (y - view.panY) * scale };
    }

    // ---- Drawing
    function render() {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          draw();
        });
      }
    }

    function currentRadius() {
      return baseRadius(view.zoom / fitZoom, n);
    }

    function draw() {
      if (!width || !height) return;
      const dotView: DotView = { ...view, baseRadius: currentRadius(), width, height, dpr };
      context!.setTransform(dpr, 0, 0, dpr, 0, 0);
      context!.clearRect(0, 0, width, height);
      if (dots) dots.draw(dotView);
      else drawDots2d(context!, data, dotView, hexColors);
      drawOverlay(dotView);
    }

    function font(size: number, weight: number) {
      return `${weight} ${size}px ${FONT_FAMILY}`;
    }

    // Dims the map, then shoots a line from a game to each similar game, most
    // similar first. A web that is fading out belongs to the previous selection.
    function drawWeb(ctx: CanvasRenderingContext2D, colors: MapPalette, radius: number) {
      if (!web) return;
      const now = performance.now();
      const still = reducedMotion.matches;
      const fade = web.fadingSince === null ? 1 : still ? 0 : 1 - (now - web.fadingSince) / WEB_FADE_MS;
      if (fade <= 0) {
        web = null;
        return;
      }
      const { zoom, panX, panY } = view;
      const { source } = web;
      const elapsed = still ? Infinity : now - web.startedAt;
      const fromX = data.xs[source] * zoom + panX;
      const fromY = data.ys[source] * zoom + panY;
      let moving = web.fadingSince !== null;

      ctx.globalAlpha = 0.6 * Math.min(1, elapsed / WEB_GROW_MS) * fade;
      ctx.fillStyle = colors.halo;
      ctx.fillRect(0, 0, width, height);

      web.targets.forEach((d, rank) => {
        const linear = Math.min(1, Math.max(0, (elapsed - rank * WEB_STAGGER_MS) / WEB_GROW_MS));
        if (linear < 1) moving = true;
        if (linear === 0) return;
        const grown = easeOut(linear);
        const x = data.xs[d] * zoom + panX;
        const y = data.ys[d] * zoom + panY;

        const gradient = ctx.createLinearGradient(fromX, fromY, x, y);
        gradient.addColorStop(0, hexColors[source]);
        gradient.addColorStop(1, hexColors[d]);
        ctx.globalAlpha = 0.9 * fade;
        ctx.lineWidth = 2;
        ctx.strokeStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(fromX, fromY);
        ctx.lineTo(fromX + (x - fromX) * grown, fromY + (y - fromY) * grown);
        ctx.stroke();
        if (linear < 1) return;

        ctx.globalAlpha = fade;
        ctx.beginPath();
        ctx.arc(x, y, Math.max(radius * data.scales[d], 3) + 1, 0, Math.PI * 2);
        ctx.fillStyle = hexColors[d];
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = colors.selected;
        ctx.stroke();
      });
      ctx.globalAlpha = 1;
      // A running camera animation already draws every frame.
      if (moving && !animation) render();
    }

    function drawOverlay(dotView: DotView) {
      const ctx = context!;
      const colors = paletteRef.current ?? readPalette(container!);
      const { zoom, panX, panY } = view;
      const radius = dotView.baseRadius;
      const selected = drawIndexById.get(selectedIdRef.current ?? NaN) ?? -1;
      const labelBottom = height - STATUS_LINE_HEIGHT;
      const placed: Box[] = [];
      ctx.textBaseline = 'middle';
      ctx.lineJoin = 'round';

      drawWeb(ctx, colors, radius);

      // Selected and hovered games get a tooltip-style label, reserved first so
      // the popular labels avoid them.
      const tips: { d: number; box: Box; textX: number; y: number; weight: number }[] = [];
      for (const [d, weight] of [[selected, 600], [hovered, 500]] as const) {
        if (d < 0 || tips.some((tip) => tip.d === d)) continue;
        const x = data.xs[d] * zoom + panX;
        const y = data.ys[d] * zoom + panY;
        const r = Math.max(radius * data.scales[d], d === selected ? 7.5 : MIN_HIT_RADIUS);
        ctx.font = font(12, weight);
        const textWidth = ctx.measureText(gameAt(d).title).width;
        let textX = x + r + 8;
        if (textX + textWidth + 6 > width) textX = x - r - 8 - textWidth; // flip left at the edge
        const box: Box = [textX - 5, y - 11, textX + textWidth + 5, y + 11];
        placed.push(box);
        tips.push({ d, box, textX, y, weight });
      }

      // Popular labels: the most reviewed games on screen, largest first; a
      // label that would overlap one already placed is skipped.
      const limit = view.zoom > fitZoom * 1.05 ? LABELS_ZOOMED : LABELS_OVERVIEW;
      let taken = 0;
      for (let d = n - 1; d >= 0 && taken < limit; d--) {
        if (d === selected || d === hovered) continue;
        const x = data.xs[d] * zoom + panX;
        const y = data.ys[d] * zoom + panY;
        if (x < 0 || y < 0 || x > width || y > labelBottom) continue;
        taken++;
        const size = labelSize(popularity[d]);
        const title = gameAt(d).title;
        ctx.font = font(size, size >= 16 ? 700 : size >= 14 ? 600 : 500);
        const textX = x + radius * data.scales[d] + 4;
        const box: Box = [textX - 2, y - size * 0.6, textX + ctx.measureText(title).width + 2, y + size * 0.6];
        if (box[3] > labelBottom || overlaps(box, placed)) continue;
        placed.push(box);
        ctx.lineWidth = size >= 14 ? Math.max(3, size / 5) : 2.5;
        ctx.strokeStyle = colors.halo;
        ctx.strokeText(title, textX, y);
        ctx.fillStyle = size >= 14 ? colors.text : colors.muted;
        ctx.fillText(title, textX, y);
      }

      // Hovered and selected dots, drawn opaque above the rest.
      for (const { d } of tips) {
        const x = data.xs[d] * zoom + panX;
        const y = data.ys[d] * zoom + panY;
        const r = radius * data.scales[d];
        ctx.beginPath();
        if (d === selected) {
          // Size and outline change too, so selection does not rely on colour (ACC 3).
          const sr = Math.max(r + 1.5, 7.5);
          ctx.fillStyle = colors.selectedUnderlay;
          ctx.arc(x, y, sr + 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.beginPath();
          ctx.arc(x, y, sr, 0, Math.PI * 2);
          ctx.fillStyle = hexColors[d];
          ctx.fill();
          ctx.lineWidth = 2.5;
          ctx.strokeStyle = colors.selected;
        } else {
          ctx.arc(x, y, Math.max(r, MIN_HIT_RADIUS), 0, Math.PI * 2);
          ctx.fillStyle = hexColors[d];
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = colors.text;
        }
        ctx.stroke();
      }
      for (const { d, box, textX, y, weight } of tips) {
        ctx.beginPath();
        ctx.roundRect(box[0], box[1], box[2] - box[0], box[3] - box[1], 4);
        ctx.fillStyle = colors.tipBackground;
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = colors.tipBorder;
        ctx.stroke();
        ctx.font = font(12, weight);
        ctx.fillStyle = colors.text;
        ctx.fillText(gameAt(d).title, textX, y);
      }
    }

    // ---- Hit testing: the topmost dot under the pointer.
    function hitTest(x: number, y: number): number {
      const radius = currentRadius();
      const reach = (Math.max(radius * maxScale, MIN_HIT_RADIUS) + HIT_SLOP) / view.zoom;
      const mx = (x - view.panX) / view.zoom;
      const my = (y - view.panY) / view.zoom;
      let best = -1;
      grid.query(mx, my, reach, (d) => {
        if (d <= best) return;
        const dx = data.xs[d] * view.zoom + view.panX - x;
        const dy = data.ys[d] * view.zoom + view.panY - y;
        const r = Math.max(radius * data.scales[d], MIN_HIT_RADIUS) + HIT_SLOP;
        if (dx * dx + dy * dy <= r * r) best = d;
      });
      return best;
    }

    function setHovered(d: number) {
      if (d === hovered) return;
      hovered = d;
      container!.style.cursor = d >= 0 ? 'pointer' : '';
      render();
    }

    // ---- Pointer input: drag to pan, pinch or wheel to zoom, click to select.
    const pointers = new Map<number, { x: number; y: number }>();
    let travel = 0;
    let pinchDistance = 0;

    function local(event: PointerEvent | WheelEvent) {
      const rect = container!.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function pinchState() {
      const [a, b] = [...pointers.values()];
      return { distance: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    }

    function onPointerDown(event: PointerEvent) {
      if (event.button !== 0) return;
      takeControl();
      try {
        container!.setPointerCapture(event.pointerId); // keep dragging when the pointer leaves the map
      } catch {
        // The pointer is already gone; the drag still works inside the map.
      }
      pointers.set(event.pointerId, local(event));
      travel = pointers.size > 1 ? CLICK_SLOP : 0;
      if (pointers.size === 2) pinchDistance = pinchState().distance;
    }

    // Last mouse position over the map, for the +/− keys.
    let pointer: { x: number; y: number } | null = null;

    function onPointerMove(event: PointerEvent) {
      const point = local(event);
      if (event.pointerType === 'mouse') pointer = point;
      const last = pointers.get(event.pointerId);
      if (!last) {
        if (event.pointerType === 'mouse') setHovered(hitTest(point.x, point.y));
        return;
      }
      if (pointers.size === 1) {
        const dx = point.x - last.x;
        const dy = point.y - last.y;
        travel += Math.hypot(dx, dy);
        pointers.set(event.pointerId, point);
        if (travel >= CLICK_SLOP) {
          takeControl();
          setHovered(-1);
          setView({ ...view, panX: view.panX + dx, panY: view.panY + dy });
        }
      } else if (pointers.size === 2) {
        takeControl();
        const before = pinchState();
        pointers.set(event.pointerId, point);
        const after = pinchState();
        const zoomed = zoomedView(pinchDistance ? after.distance / pinchDistance : 1, after.x, after.y);
        pinchDistance = after.distance;
        setView({ ...zoomed, panX: zoomed.panX + after.x - before.x, panY: zoomed.panY + after.y - before.y });
      }
    }

    function onPointerUp(event: PointerEvent) {
      if (!pointers.has(event.pointerId)) return;
      const wasClick = pointers.size === 1 && travel < CLICK_SLOP && event.type === 'pointerup';
      pointers.delete(event.pointerId);
      if (wasClick) {
        const point = local(event);
        const d = hitTest(point.x, point.y);
        if (d >= 0) onSelectRef.current(gameAt(d));
        else onClickBackgroundRef.current();
      }
    }

    function onWheel(event: WheelEvent) {
      event.preventDefault();
      takeControl();
      const point = local(event);
      const rate = event.deltaMode ? WHEEL_LINE_ZOOM_RATE : event.ctrlKey ? PINCH_ZOOM_RATE : WHEEL_ZOOM_RATE;
      const factor = Math.exp(-event.deltaY * rate);
      setView(zoomedView(factor, point.x, point.y));
    }

    container.addEventListener('pointerdown', onPointerDown);
    container.addEventListener('pointermove', onPointerMove);
    container.addEventListener('pointerup', onPointerUp);
    container.addEventListener('pointercancel', onPointerUp);
    const onPointerLeave = () => {
      pointer = null;
      setHovered(-1);
    };
    container.addEventListener('pointerleave', onPointerLeave);
    container.addEventListener('wheel', onWheel, { passive: false });

    // Keyboard: arrows pan, + zooms toward the mouse, − zooms out from the
    // centre. Works while the map has
    // focus or the mouse is over it, so clicking a game (which moves focus to
    // the info panel) does not switch the keys off. Typing in a field wins.
    const KEY_PANS: Record<string, [number, number]> = {
      ArrowLeft: [KEY_PAN_STEP, 0],
      ArrowRight: [-KEY_PAN_STEP, 0],
      ArrowUp: [0, KEY_PAN_STEP],
      ArrowDown: [0, -KEY_PAN_STEP],
    };
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="listbox"]')) return;
      if (document.activeElement !== container && pointer === null) return;
      const pan = KEY_PANS[event.key];
      if (pan) {
        // Arrow keys only belong to the map when it has focus; elsewhere they
        // scroll panels and move through lists.
        if (document.activeElement !== container) return;
        takeControl();
        setView({ ...view, panX: view.panX + pan[0], panY: view.panY + pan[1] });
      } else if (event.key === '+' || event.key === '=') {
        controllerRef.current?.zoomAtPointer(ZOOM_STEP);
      } else if (event.key === '-' || event.key === '_') {
        // Zooming out always keeps the centre still, wherever the mouse is.
        controllerRef.current?.zoomAround(1 / ZOOM_STEP, width / 2, height / 2, false);
      } else {
        return;
      }
      event.preventDefault();
    }
    window.addEventListener('keydown', onKeyDown);

    // ---- Size
    function resize() {
      const nextWidth = container!.clientWidth;
      const nextHeight = container!.clientHeight;
      if (!nextWidth || !nextHeight) return;
      width = nextWidth;
      height = nextHeight;
      dpr = window.devicePixelRatio || 1;
      for (const canvas of [dotCanvas!, labelCanvas!]) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      fitZoom = fitView().zoom;
      view = fitted ? clamp(view) : fitView();
      fitted = true;
      draw(); // resizing clears the canvases, so redraw now rather than next frame
    }
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    controllerRef.current = {
      zoomAround(factor, x, y, animate) {
        takeControl();
        const next = zoomedView(factor, x, y);
        if (animate) animateTo(next);
        else setView(next);
      },
      zoomAtPointer(factor) {
        takeControl();
        const { x, y } = pointer ?? { x: width / 2, y: height / 2 };
        setView(zoomedView(factor, x, y));
      },
      fit() {
        takeControl();
        animateTo(fitView());
      },
      focusGame(id, obscuredRight) {
        const d = drawIndexById.get(id);
        if (d === undefined) return;
        const zoom = clampZoom(Math.max(view.zoom, fitZoom * FOCUS_ZOOM_FACTOR));
        animateTo({
          zoom,
          panX: visibleWidth(obscuredRight) / 2 - data.xs[d] * zoom,
          panY: height / 2 - data.ys[d] * zoom,
        }, GLIDE_MS, easeInOut);
      },
      setWeb(selectedId, similarGames, obscuredRight) {
        if (selectedId !== trackedSelection) {
          trackedSelection = selectedId;
          movesAtSelection = userMoves;
        }
        const source = drawIndexById.get(selectedId ?? NaN);
        const targets: number[] = [];
        if (source !== undefined) {
          for (const { id } of similarGames ?? []) {
            const d = drawIndexById.get(id);
            if (d !== undefined) targets.push(d);
          }
        }
        if (source === undefined || targets.length === 0) {
          if (web && web.fadingSince === null) web.fadingSince = performance.now();
          return;
        }
        const shown = web && web.fadingSince === null && web.source === source
          && web.targets.length === targets.length && web.targets.every((d, i) => d === targets[i]);
        if (shown) return;

        web = { source, targets, startedAt: performance.now(), fadingSince: null };
        if (userMoves !== movesAtSelection) return;
        const xs = [source, ...targets].map((d) => data.xs[d]);
        const ys = [source, ...targets].map((d) => data.ys[d]);
        animateTo(
          viewForBox(
            Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys),
            visibleWidth(obscuredRight), WEB_PADDING, clampZoom,
          ),
          GLIDE_MS,
          easeInOut,
        );
      },
      render,
    };

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      stopAnimation();
      container.removeEventListener('pointerdown', onPointerDown);
      container.removeEventListener('pointermove', onPointerMove);
      container.removeEventListener('pointerup', onPointerUp);
      container.removeEventListener('pointercancel', onPointerUp);
      container.removeEventListener('pointerleave', onPointerLeave);
      container.removeEventListener('wheel', onWheel);
      window.removeEventListener('keydown', onKeyDown);
      container.style.cursor = '';
      dots?.dispose();
      controllerRef.current = null;
    };
  }, [games]);

  // Selecting a game redraws the overlay at once. The view moves when the
  // game's similar games arrive.
  useEffect(() => {
    selectedIdRef.current = selectedId;
    controllerRef.current?.setWeb(selectedId, similarGames, obscuredRight);
    controllerRef.current?.render();
  }, [games, selectedId, similarGames, obscuredRight]);

  // main.tsx switches the CSS variables before React re-renders, so they are current here.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    paletteRef.current = readPalette(container);
    controllerRef.current?.render();
  }, [themeMode]);

  useImperativeHandle(ref, () => {
    function centre() {
      const container = containerRef.current;
      return { x: (container?.clientWidth ?? 0) / 2, y: (container?.clientHeight ?? 0) / 2 };
    }
    return {
      zoomIn() {
        const { x, y } = centre();
        controllerRef.current?.zoomAround(ZOOM_STEP, x, y, true);
      },
      zoomOut() {
        const { x, y } = centre();
        controllerRef.current?.zoomAround(1 / ZOOM_STEP, x, y, true);
      },
      resetView() {
        controllerRef.current?.fit();
      },
      focusGame(id, obscuredRight = 0) {
        controllerRef.current?.focusGame(id, obscuredRight);
      },
      focus() {
        containerRef.current?.focus();
      },
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="game-map-canvas"
      tabIndex={0}
      role="region"
      aria-label="Game map"
      aria-describedby="map-instructions"
    >
      <canvas ref={dotCanvasRef} aria-hidden="true" />
      <canvas ref={labelCanvasRef} aria-hidden="true" />
    </div>
  );
}
