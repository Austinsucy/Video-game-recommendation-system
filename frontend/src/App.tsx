import './shell.css';

export default function App() {
  return (
    <div className="app-shell">
      <header className="site-header">
        <h1>A Gooner's Interactive Game Map</h1>
        <p>Discover games through an interactive map.</p>
      </header>

      <nav className="toolbar" aria-label="Game discovery controls">
        <input
          aria-label="Search games"
          placeholder="Search games..."
          disabled
        />

        <select aria-label="Genre" disabled>
          <option>All genres</option>
        </select>

        <button disabled>Scan</button>
      </nav>

      <main className="workspace">
        <section className="map-placeholder">
          <h2>Game map</h2>
          <p>Sample game nodes will appear here.</p>
        </section>

        <aside className="information-panel">
          <h2>Game information</h2>
          <p>Select a game to view its details. e.g. Title, Genre, Number of Players, etc. </p>

          <div className="cover-placeholder">Cover image</div>

          <p>Title: —</p>
          <p>Release year: —</p>
          <p>Genres: —</p>
          <p>Description: —</p>
        </aside>
      </main>
    </div>
  );
}

