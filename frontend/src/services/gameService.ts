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

// The GIP 1 fields. map.db has none of the fields below `MapGame`; they will
// come from FastAPI GET /games/{id}. Until then they are null or empty and the
// panel labels them unavailable.
export interface GameDetails extends MapGame {
  coverUrl: string | null;
  releaseYear: number | null;
  description: string | null;
  tags: string[];
  platforms: string[];
  rating: string | null;
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

export async function getGameDetails(id: number): Promise<GameDetails> {
  // These details were already loaded from map.db. Clicking needs no fetch.
  // Replace the defaults below with the GET /games/{id} response when the
  // backend exists, keeping this function's signature.
  const { games } = await getMap();
  const game = games.find((record) => record.id === id);
  if (!game) throw new Error('This game is not in the map database.');
  return {
    ...game,
    coverUrl: null,
    releaseYear: null,
    description: null,
    tags: [],
    platforms: [],
    rating: null,
    averagePlaytimeHours: null,
    storeUrl: null,
    similarGames: [],
  };
}
