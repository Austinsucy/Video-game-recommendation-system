import type { StylesheetJson } from 'cytoscape';

// Sizes are in screen pixels. Cytoscape scales everything with the zoom, so
// buildMapStyle divides by the zoom to keep nodes and labels the same size on
// screen. Zooming in then spreads crowded nodes apart instead of enlarging them.
export const NODE_SIZE = 9;
export const SELECTED_NODE_SIZE = 15;
export const LABEL_FONT_SIZE = 12;
export const LABEL_MAX_WIDTH = 170;
export const LABEL_GAP = 3;
export const LABEL_FONT = `500 ${LABEL_FONT_SIZE}px "Inter", "Segoe UI", system-ui, sans-serif`;

const TEXT = '#1f2937';
const SELECTED = '#111827';
const HALO = '#f7f7f5';

export function buildMapStyle(zoom: number): StylesheetJson {
  const px = (value: number) => value / zoom;
  const label = {
    label: 'data(title)',
    color: TEXT,
    'font-family': '"Inter", "Segoe UI", system-ui, sans-serif',
    'font-weight': 500,
    'font-size': px(LABEL_FONT_SIZE),
    'text-valign': 'top',
    'text-halign': 'center',
    'text-margin-y': px(-LABEL_GAP),
    'text-wrap': 'ellipsis',
    'text-max-width': `${px(LABEL_MAX_WIDTH)}px`,
    'text-outline-color': HALO,
    'text-outline-width': px(2.5),
    'text-outline-opacity': 1,
  } as const;
  const tooltip = {
    ...label,
    'text-outline-width': 0,
    'text-background-color': '#ffffff',
    'text-background-opacity': 1,
    'text-background-padding': `${px(4)}px`,
    'text-background-shape': 'roundrectangle',
    'text-border-color': '#d4d4cf',
    'text-border-width': px(1),
    'text-border-opacity': 1,
    'text-margin-y': px(-LABEL_GAP - 4),
  } as const;

  return [
    {
      selector: 'node',
      style: {
        width: px(NODE_SIZE),
        height: px(NODE_SIZE),
        'background-color': 'data(color)',
        'background-opacity': 0.9,
        'border-color': '#ffffff',
        'border-width': px(1),
        label: '',
      },
    },
    // Labels chosen by labelPlacement: the most popular games that fit
    // on screen without overlapping.
    // A higher z-index draws these labels above neighbouring dots.
    { selector: 'node.has-label', style: { ...label, 'z-index': 10 } },
    { selector: 'node.is-hovered', style: { ...tooltip, 'z-index': 20 } },
    {
      // Size and outline change too, so selection does not rely on colour (ACC 3).
      selector: 'node.is-selected',
      style: {
        ...tooltip,
        'font-weight': 600,
        width: px(SELECTED_NODE_SIZE),
        height: px(SELECTED_NODE_SIZE),
        'border-color': SELECTED,
        'border-width': px(2.5),
        'background-opacity': 1,
        'underlay-color': '#1d4ed8',
        'underlay-opacity': 0.16,
        'underlay-padding': px(7),
        'underlay-shape': 'ellipse',
        'text-margin-y': px(-LABEL_GAP - 6),
        'z-index': 30,
      },
    },
  ];
}
