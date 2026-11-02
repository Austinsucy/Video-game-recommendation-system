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

export interface GameDetails extends MapGame {
  // map.db has no values for these fields. A later backend can supply them.
  releaseYear: number | null;
  players: string | null;
  description: string | null;
  coverUrl: string | null;
}

let mapRequest: Promise<MapGame[]> | null = null;

export function getMapGames(): Promise<MapGame[]> {
  if (!mapRequest) {
    mapRequest = readMapGames().catch((error: unknown) => {
      mapRequest = null;
      throw error;
    });
  }
  return mapRequest;
}

async function readMapGames(): Promise<MapGame[]> {
  const db = await getMapDatabase();
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
  return rows.map(([id, title, x, y, clusterId, clusterName, color, popularity]) => {
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
        popularity: typeof popularity === 'number' ? popularity : null,
        genres: genresById.get(id) ?? [],
    };
  });
}

export async function getGameDetails(id: number): Promise<GameDetails> {
  // These details were already loaded from map.db. Clicking needs no fetch.
  const games = await getMapGames();
  const game = games.find((record) => record.id === id);
  if (!game) throw new Error('This game is not in the map database.');
  return {
    ...game,
    releaseYear: null,
    players: null,
    description: null,
    coverUrl: null,
  };
}
