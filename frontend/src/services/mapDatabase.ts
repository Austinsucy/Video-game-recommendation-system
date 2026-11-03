import initSqlJs, { type Database } from 'sql.js';
import wasmUrl from 'sql.js/dist/sql-wasm.wasm?url';
// The ML pipeline writes data/map.db. Vite serves it in dev and copies it into the build.
import mapDatabaseUrl from '../../../data/map.db?url';

// All callers share this promise, including React Strict Mode's initial effects.
// The database stays in memory until the page is reloaded or closed.
let databaseRequest: Promise<Database> | null = null;

export function getMapDatabase(): Promise<Database> {
  if (!databaseRequest) {
    databaseRequest = (async () => {
      const [SQL, response] = await Promise.all([
        initSqlJs({ locateFile: () => wasmUrl }),
        fetch(mapDatabaseUrl),
      ]);
      if (!response.ok) throw new Error('The map database could not load.');
      const bytes = new Uint8Array(await response.arrayBuffer());
      const db = new SQL.Database(bytes);
      try {
        // This downloaded snapshot is only used for reading.
        db.exec('PRAGMA query_only = ON');
        return db;
      } catch (error) {
        db.close();
        throw error;
      }
    })().catch((error: unknown) => {
      databaseRequest = null;
      throw error;
    });
  }
  return databaseRequest;
}
