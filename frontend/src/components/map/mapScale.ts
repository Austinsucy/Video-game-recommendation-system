import type { MapGame } from '../../services/gameService';

// Popularity sizing, matching the Tag Vector Lab's "By Steam reviews" view.
// popularity is the Steam review count; -1 or null means unknown and counts as 0.
//   t = (log(1 + reviews) / log(1 + most reviews)) ^ 2.5
// The power keeps most games small so only the best known stand out.
const POPULARITY_EXPONENT = 2.5;
// The lab's size scale is 3; 2.5 draws dots and labels a little smaller.
const SIZE_BOOST = 2.5;
const LARGE_MAP_FACTOR = 1.8; // the lab enlarges dots on maps over 5,000 games

/** Popularity from 0 (no reviews) to 1 (most reviewed game). */
export function popularityScores(games: MapGame[]): Float32Array {
  const logs = games.map((game) => Math.log1p(Math.max(0, game.popularity ?? 0)));
  const maxLog = logs.reduce((max, value) => Math.max(max, value), 0) || 1;
  return Float32Array.from(logs, (value) => (value / maxLog) ** POPULARITY_EXPONENT);
}

/** Dot radius multiplier for a popularity score. */
export function dotScale(t: number, gameCount: number): number {
  return (0.35 + SIZE_BOOST * 2.5 * t) * (gameCount > 5000 ? LARGE_MAP_FACTOR : 1);
}

/**
 * Base dot radius in screen px for a zoom relative to the fitted view. Dots
 * grow a little when zooming in, so crowded areas spread apart.
 */
export function baseRadius(relativeZoom: number, gameCount: number): number {
  return gameCount > 5000
    ? Math.min(3, 0.9 * Math.sqrt(relativeZoom))
    : Math.min(5, 2.6 * Math.cbrt(relativeZoom));
}

/** Label font size in px for a popularity score. */
export function labelSize(t: number): number {
  return Math.round(10 + SIZE_BOOST * 4.5 * t);
}

/**
 * Uniform grid over model coordinates for hit testing. `query` calls `visit`
 * with the index of every point in the cells that overlap the square around
 * (x, y).
 */
export class PointGrid {
  private readonly cellSize: number;
  private readonly minX: number;
  private readonly minY: number;
  private readonly cols: number;
  private readonly rows: number;
  private readonly cellStart: Int32Array;
  private readonly items: Int32Array;

  constructor(xs: Float32Array, ys: Float32Array) {
    const n = xs.length;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (let i = 0; i < n; i++) {
      minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i]);
      minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i]);
    }
    if (!n) { minX = minY = 0; maxX = maxY = 1; }
    // About two points per cell on average.
    const area = Math.max(maxX - minX, 1) * Math.max(maxY - minY, 1);
    this.cellSize = Math.max(Math.sqrt((area * 2) / Math.max(n, 1)), 1e-6);
    this.minX = minX;
    this.minY = minY;
    this.cols = Math.floor((maxX - minX) / this.cellSize) + 1;
    this.rows = Math.floor((maxY - minY) / this.cellSize) + 1;

    // Counting sort of point indexes by cell.
    const cellOf = new Int32Array(n);
    this.cellStart = new Int32Array(this.cols * this.rows + 1);
    for (let i = 0; i < n; i++) {
      const cell = this.cellIndex(this.col(xs[i]), this.row(ys[i]));
      cellOf[i] = cell;
      this.cellStart[cell + 1]++;
    }
    for (let c = 0; c < this.cols * this.rows; c++) this.cellStart[c + 1] += this.cellStart[c];
    const fill = this.cellStart.slice(0, -1);
    this.items = new Int32Array(n);
    for (let i = 0; i < n; i++) this.items[fill[cellOf[i]]++] = i;
  }

  private col(x: number) {
    return Math.min(this.cols - 1, Math.max(0, Math.floor((x - this.minX) / this.cellSize)));
  }

  private row(y: number) {
    return Math.min(this.rows - 1, Math.max(0, Math.floor((y - this.minY) / this.cellSize)));
  }

  private cellIndex(col: number, row: number) {
    return row * this.cols + col;
  }

  query(x: number, y: number, radius: number, visit: (index: number) => void) {
    const c0 = this.col(x - radius), c1 = this.col(x + radius);
    const r0 = this.row(y - radius), r1 = this.row(y + radius);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const cell = this.cellIndex(c, r);
        for (let k = this.cellStart[cell]; k < this.cellStart[cell + 1]; k++) visit(this.items[k]);
      }
    }
  }
}
