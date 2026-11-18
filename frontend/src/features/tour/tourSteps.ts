import type { FeatureStatus } from '../featureStatus';
import { featureButtonId, type FeatureId } from '../features';

/** Where the tour card sits relative to the highlighted element. */
export type TourPlacement = 'bottom' | 'top' | 'left' | 'center';

export interface TourStep {
  title: string;
  body: string;
  /**
   * CSS selector for the element to highlight. Leave it out for a step that
   * shows only the card in the middle of the screen. If the element is not
   * on the page (for example the map is still loading), the card is centred
   * and nothing is highlighted.
   */
  target?: string;
  placement?: TourPlacement;
  /** Shown as a chip so users know a feature is unfinished. Keep in step with each panel's `status`. */
  status?: FeatureStatus;
}

const button = (id: FeatureId) => `#${featureButtonId(id)}`;

// GW 1: guided tour. Add, remove or reorder steps here; the tour itself
// needs no changes. When a feature ships, update its `status`.
export const TOUR_STEPS: TourStep[] = [
  {
    title: 'Welcome to Our Game Map!',
    body: 'This short tour shows you around the map and the toolbar. Use the arrow buttons or the ← and → keys to move through it, and skip it using the bottom button at any time.',
  },
  {
    title: 'The Map',
    body: 'Each dot is a game. Games with similar genres, mechanics and themes sit close together, and colors mark groups of similar games. Drag to pan, scroll to zoom and click a dot to see the game’s details.',
    target: '.game-map-canvas',
    placement: 'center',
  },
  {
    title: 'Search',
    body: 'Type a title to find a game. The map moves to it and opens its information.',
    target: '.search-box',
    placement: 'bottom',
  },
  {
    title: 'Recommendations',
    body: 'Rank how much each kind of feature matters to you, such as genres, mechanics and themes, then generate a personal map built around your tastes.',
    target: button('recommendations'),
    placement: 'bottom',
    status: 'planned',
  },
  {
    title: 'Genres',
    body: 'Choose one genre to fade out the other games on the map. The games keep their positions, so you can see where your chosen genre sits on the map.',
    target: button('genres'),
    placement: 'bottom',
    status: 'available',
  },
  {
    title: 'Legend',
    body: 'See what each color cluster means. Every color is a cluster of games with similar features.',
    target: button('legend'),
    placement: 'bottom',
    status: 'partial',
  },
  {
    title: 'Scan',
    body: 'Not sure what to play? Scan jumps from one random game to the next, opening each one, until you press Stop. Scan also accounts for your genre filter.',
    target: button('scan'),
    placement: 'bottom',
    status: 'partial',
  },
  {
    title: 'Save / Share',
    body: 'Save your selected game, genre filter and recommendation settings, or copy a link that restores them for a friend.',
    target: button('share'),
    placement: 'bottom',
    status: 'planned',
  },
  {
    title: 'Steam Library',
    body: 'Enter a public Steam ID to see the games you own on the map and get recommendations from them. *We will never ask you for your password*',
    target: button('steam'),
    placement: 'bottom',
    status: 'planned',
  },
  {
    title: 'Zoom and reset',
    body: 'Zoom in and out here. Reset view brings every game back on screen if you get lost.',
    target: '.map-controls',
    placement: 'left',
  },
  {
    title: 'Light and dark mode',
    body: 'Switch between a light and a dark map.',
    target: '.theme-toggle',
    placement: 'bottom',
  },
  {
    title: 'You’re all set!',
    body: 'Help lists every map control, and you can restart this tour from there any time.',
    target: button('help'),
    placement: 'bottom',
  },
];
