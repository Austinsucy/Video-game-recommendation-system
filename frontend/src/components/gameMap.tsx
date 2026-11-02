import { useEffect, useRef } from 'react';
import cytoscape, { type Core } from 'cytoscape';
import type { MapGame } from '../services/gameService';

interface GameMapProps {
  games: MapGame[];
  selectedId: number | null;
  onSelectGame: (game: MapGame) => void;
}

export default function GameMap({ games, selectedId, onSelectGame }: GameMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelectGame);

  useEffect(() => {
    onSelectRef.current = onSelectGame;
  }, [onSelectGame]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const gamesById = new Map(games.map((game) => [String(game.id), game]));
    const map = cytoscape({
      container,
      elements: games.map((game) => ({
        data: {
          id: String(game.id),
          title: game.title,
          color: game.clusterColor,
        },
        position: { x: game.x, y: game.y },
      })),
      // Preset uses the algorithm's stored positions instead of calculating new ones.
      layout: { name: 'preset', fit: true, padding: 40 },
      autoungrabify: true,
      autounselectify: true,
      boxSelectionEnabled: false,
      minZoom: 0.05,
      maxZoom: 8,
      style: [
        {
          selector: 'node',
          style: {
            width: 18,
            height: 18,
            'background-color': 'data(color)',
            'border-color': '#ffffff',
            'border-width': 1,
            label: '',
          },
        },
        {
          selector: 'node.is-selected',
          style: {
            width: 26,
            height: 26,
            'border-color': '#111827',
            'border-width': 4,
            label: 'data(title)',
            color: '#111827',
            'font-size': 16,
            'text-valign': 'top',
            'text-margin-y': -8,
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.95,
            'text-background-padding': '4px',
            'z-index': 10,
          },
        },
      ],
    });
    mapRef.current = map;

    map.on('tap', 'node', (event) => {
      const game = gamesById.get(event.target.id());
      if (game) onSelectRef.current(game);
    });

    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container);

    return () => {
      observer.disconnect();
      mapRef.current = null;
      map.destroy();
    };
  }, [games]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.nodes().removeClass('is-selected');
    if (selectedId !== null) {
      map.getElementById(String(selectedId)).addClass('is-selected');
    }
  }, [games, selectedId]);

  return (
    <div
      ref={containerRef}
      className="game-map-canvas"
      style={{ position: 'absolute', inset: 0 }}
      tabIndex={0}
      role="region"
      aria-label="Interactive game map. Drag the background to pan and scroll to zoom. Select a game node, or use the game selector in the toolbar."
    />
  );
}