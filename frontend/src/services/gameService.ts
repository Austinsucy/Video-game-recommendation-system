import { getMapDatabase } from './mapDatabase';

export interface GameSummary {
  id: number;
  title: string;
}

export interface MapGame extends GameSummary {
  x: number;
  y: number;
  clusterId: number;
  clusterName: string;
  clusterColor: string;
  popularity: number | null;
  genres: string[];
}

export interface MapData {
  version: string;
  games: MapGame[];
}

// The GIP 1 fields, as FastAPI GET /games/{id} returns them.
export interface GameDetails {
  id: number;
  coverUrl: string | null;
  releaseYear: number | null;
  description: string | null;
  tags: string[];
  platforms: string[];
  rating: number | null;
  ratingMax: number | null;
  averagePlaytimeHours: number | null;
  storeUrl: string | null;
  similarGames: GameSummary[];
}

let mapRequest: Promise<MapData> | null = null;

export function getMap(): Promise<MapData> {
  if (!mapRequest) {
    mapRequest = readMap().catch((error: unknown) => {
      mapRequest = null;
      throw error;
    });
  }
  return mapRequest;
}

async function readMap(): Promise<MapData> {
  const db = await getMapDatabase();
  const version = db.exec('SELECT map_version FROM map_info LIMIT 1')[0]?.values[0]?.[0];
  if (typeof version !== 'string' || !version) {
    throw new Error('Invalid map data. The map version is missing.');
  }
  const genreRows = db.exec(`
    SELECT game_id, genre FROM game_genres ORDER BY game_id, genre
  `)[0]?.values ?? [];
  const genresById = new Map<number, string[]>();
  for (const [id, genre] of genreRows) {
    if (typeof id !== 'number' || typeof genre !== 'string') {
      throw new Error('Invalid genre data.');
    }
    const genres = genresById.get(id) ?? [];
    genres.push(genre);
    genresById.set(id, genres);
  }

  // LEFT JOIN keeps every game so a missing cluster fails validation rather
  // than silently dropping that game from the map.
  const rows = db.exec(`
    SELECT g.game_id, g.title, g.x, g.y, g.cluster_id,
           c.name, c.color, g.popularity
    FROM games AS g
    LEFT JOIN clusters AS c ON c.cluster_id = g.cluster_id
    ORDER BY g.game_id
  `)[0]?.values ?? [];
  const ids = new Set<number>();

  // Validate every row before returning the map to React.
  const games = rows.map(([id, title, x, y, clusterId, clusterName, color, popularity]) => {
    if (
      typeof id !== 'number' || !Number.isSafeInteger(id) || ids.has(id) ||
      typeof title !== 'string' || !title.trim() ||
      typeof x !== 'number' || !Number.isFinite(x) ||
      typeof y !== 'number' || !Number.isFinite(y) ||
      typeof clusterId !== 'number' || !Number.isSafeInteger(clusterId) ||
      typeof clusterName !== 'string' ||
      typeof color !== 'string' || !/^#[0-9a-f]{6}$/i.test(color) ||
      (popularity !== null &&
        (typeof popularity !== 'number' || !Number.isFinite(popularity)))
    ) {
      throw new Error('Invalid map data. The map was not displayed.');
    }
    ids.add(id);
    return {
        id,
        title,
        x,
        y,
        clusterId,
        clusterName,
        clusterColor: color,
        // map.db stores -1 when Steam's review count is unknown.
        popularity: typeof popularity === 'number' && popularity >= 0 ? popularity : null,
        genres: genresById.get(id) ?? [],
    };
  });
  return { version, games };
}

const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const isString = (value: unknown): value is string => typeof value === 'string';
const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);
const orNull = <T>(value: unknown, is: (v: unknown) => v is T): value is T | null =>
  value === null || is(value);
const listOf = <T>(value: unknown, is: (v: unknown) => v is T): value is T[] =>
  Array.isArray(value) && value.every(is);

function isGameSummary(value: unknown): value is GameSummary {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return isNumber(v.id) && isString(v.title);
}

function parseGameDetails(value: unknown): GameDetails | null {
  if (typeof value !== 'object' || value === null) return null;
  const {
    id, coverUrl, releaseYear, description, tags, platforms,
    rating, ratingMax, averagePlaytimeHours, storeUrl, similarGames,
  } = value as Record<string, unknown>;
  if (
    !isNumber(id) ||
    !orNull(coverUrl, isString) ||
    !orNull(releaseYear, isNumber) ||
    !orNull(description, isString) ||
    !listOf(tags, isString) ||
    !listOf(platforms, isString) ||
    !orNull(rating, isNumber) ||
    !orNull(ratingMax, isNumber) ||
    !orNull(averagePlaytimeHours, isNumber) ||
    !orNull(storeUrl, isString) ||
    !listOf(similarGames, isGameSummary)
  ) {
    return null;
  }
  return {
    id, coverUrl, releaseYear, description, tags, platforms,
    rating, ratingMax, averagePlaytimeHours, storeUrl,
    similarGames: similarGames.map((game) => ({ id: game.id, title: game.title })),
  };
}

export async function getGameDetails(id: number): Promise<GameDetails> {
  const response = await fetch(`${API_BASE_URL}/games/${id}`);
  if (!response.ok) {
    throw new Error(`The game details request failed (${response.status}).`);
  }
  const details = parseGameDetails(await response.json());
  if (!details || details.id !== id) {
    throw new Error('Invalid game details response.');
  }
  return details;
}
