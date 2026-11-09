import { useEffect, useImperativeHandle, useRef, type KeyboardEvent, type Ref } from 'react';
import type { MapGame } from '../../services/gameService';
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
  onSelectGame: (game: MapGame) => void;
  /** Redraws the labels and highlights in the new theme's colours. */
  themeMode: ThemeMode;
  ref?: Ref<GameMapHandle>;
}

const FIT_PADDING = 40;
const MIN_ZOOM_FACTOR = 0.6; // relative to the fitted zoom
const MAX_ZOOM_FACTOR = 30;
const FOCUS_ZOOM_FACTOR = 5;
const ZOOM_STEP = 1.5;
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
  panBy(dx: number, dy: number): void;
  fit(): void;
  focusGame(id: number, obscuredRight: number): void;
  render(): void;
}

type Box = [left: number, top: number, right: number, bottom: number];

function overlaps(box: Box, placed: Box[]) {
  return placed.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1]);
}

function hexToRgb(hex: string): [number, number, number] {
  const value = parseInt(hex.slice(1), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}

export default function GameMap({ games, selectedId, onSelectGame, themeMode, ref }: GameMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dotCanvasRef = useRef<HTMLCanvasElement>(null);
  const labelCanvasRef = useRef<HTMLCanvasElement>(null);
  const controllerRef = useRef<MapController | null>(null);
  const onSelectRef = useRef(onSelectGame);
  const selectedIdRef = useRef(selectedId);
  const paletteRef = useRef<MapPalette | null>(null);

  useEffect(() => {
    onSelectRef.current = onSelectGame;
  }, [onSelectGame]);

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

    function fitView(): View {
      const spanX = Math.max(maxX - minX, 1e-6);
      const spanY = Math.max(maxY - minY, 1e-6);
      const zoom = Math.max(
        Math.min((width - 2 * FIT_PADDING) / spanX, (height - 2 * FIT_PADDING) / spanY),
        1e-6,
      );
      return {
        zoom,
        panX: width / 2 - ((minX + maxX) / 2) * zoom,
        panY: height / 2 - ((minY + maxY) / 2) * zoom,
      };
    }

    // Zoom limits, and at least PAN_MARGIN px of the map on screen (bounded pan, GM 2).
    function clamp(next: View): View {
      const zoom = Math.min(fitZoom * MAX_ZOOM_FACTOR, Math.max(fitZoom * MIN_ZOOM_FACTOR, next.zoom));
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

    function animateTo(target: View) {
      stopAnimation();
      const from = view;
      const to = clamp(target);
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / ANIMATION_MS);
        const e = 1 - (1 - t) ** 3; // ease-out cubic
        view = {
          zoom: from.zoom + (to.zoom - from.zoom) * e,
          panX: from.panX + (to.panX - from.panX) * e,
          panY: from.panY + (to.panY - from.panY) * e,
        };
        draw();
        animation = t < 1 ? requestAnimationFrame(step) : 0;
      };
      animation = requestAnimationFrame(step);
    }

    function zoomedView(factor: number, x: number, y: number): View {
      const zoom = Math.min(fitZoom * MAX_ZOOM_FACTOR, Math.max(fitZoom * MIN_ZOOM_FACTOR, view.zoom * factor));
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
      stopAnimation();
      try {
        container!.setPointerCapture(event.pointerId); // keep dragging when the pointer leaves the map
      } catch {
        // The pointer is already gone; the drag still works inside the map.
      }
      pointers.set(event.pointerId, local(event));
      travel = pointers.size > 1 ? CLICK_SLOP : 0;
      if (pointers.size === 2) pinchDistance = pinchState().distance;
    }

    function onPointerMove(event: PointerEvent) {
      const point = local(event);
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
          setHovered(-1);
          setView({ ...view, panX: view.panX + dx, panY: view.panY + dy });
        }
      } else if (pointers.size === 2) {
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
      }
    }

    function onWheel(event: WheelEvent) {
      event.preventDefault();
      stopAnimation();
      const point = local(event);
      const factor = Math.exp(-event.deltaY * (event.deltaMode ? 0.05 : 0.0015));
      setView(zoomedView(factor, point.x, point.y));
    }

    container.addEventListener('pointerdown', onPointerDown);
    container.addEventListener('pointermove', onPointerMove);
    container.addEventListener('pointerup', onPointerUp);
    container.addEventListener('pointercancel', onPointerUp);
    const onPointerLeave = () => setHovered(-1);
    container.addEventListener('pointerleave', onPointerLeave);
    container.addEventListener('wheel', onWheel, { passive: false });

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
        const next = zoomedView(factor, x, y);
        if (animate) animateTo(next);
        else setView(next);
      },
      panBy(dx, dy) {
        stopAnimation();
        setView({ ...view, panX: view.panX + dx, panY: view.panY + dy });
      },
      fit() {
        animateTo(fitView());
      },
      focusGame(id, obscuredRight) {
        const d = drawIndexById.get(id);
        if (d === undefined) return;
        const zoom = Math.min(fitZoom * MAX_ZOOM_FACTOR, Math.max(view.zoom, fitZoom * FOCUS_ZOOM_FACTOR));
        const visibleWidth = Math.max(width - obscuredRight, width / 2);
        animateTo({
          zoom,
          panX: visibleWidth / 2 - data.xs[d] * zoom,
          panY: height / 2 - data.ys[d] * zoom,
        });
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
      container.style.cursor = '';
      dots?.dispose();
      controllerRef.current = null;
    };
  }, [games]);

  // Selection only redraws the overlay, so the viewport stays where the user left it.
  useEffect(() => {
    selectedIdRef.current = selectedId;
    controllerRef.current?.render();
  }, [games, selectedId]);

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

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const controller = controllerRef.current;
    if (!controller || event.target !== event.currentTarget) return;
    const pans: Record<string, [number, number]> = {
      ArrowLeft: [KEY_PAN_STEP, 0],
      ArrowRight: [-KEY_PAN_STEP, 0],
      ArrowUp: [0, KEY_PAN_STEP],
      ArrowDown: [0, -KEY_PAN_STEP],
    };
    const step = pans[event.key];
    const { clientWidth, clientHeight } = event.currentTarget;
    if (step) {
      controller.panBy(step[0], step[1]);
    } else if (event.key === '+' || event.key === '=') {
      controller.zoomAround(ZOOM_STEP, clientWidth / 2, clientHeight / 2, false);
    } else if (event.key === '-' || event.key === '_') {
      controller.zoomAround(1 / ZOOM_STEP, clientWidth / 2, clientHeight / 2, false);
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
    >
      <canvas ref={dotCanvasRef} aria-hidden="true" />
      <canvas ref={labelCanvasRef} aria-hidden="true" />
    </div>
  );
}
