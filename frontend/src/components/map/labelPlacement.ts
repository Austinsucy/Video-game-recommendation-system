export interface LabelCandidate {
  id: string;
  /** Node centre in screen pixels. */
  x: number;
  y: number;
  /** Label text width in screen pixels. */
  width: number;
}

export interface LabelLayout {
  viewWidth: number;
  viewHeight: number;
  labelHeight: number;
  /** Distance from the node centre to the bottom of its label. */
  offset: number;
  /** Extra space kept clear around every label. */
  padding: number;
  maxLabels: number;
}

interface Box { left: number; right: number; top: number; bottom: number; }

/**
 * Greedy label placement. Candidates arrive in priority order (most popular
 * first); each label is kept only if it is fully on screen and does not
 * overlap a label already kept. Returns the ids of the labelled nodes.
 */
export function placeLabels(candidates: Iterable<LabelCandidate>, layout: LabelLayout): string[] {
  const kept: Box[] = [];
  const ids: string[] = [];
  for (const candidate of candidates) {
    if (ids.length >= layout.maxLabels) break;
    const box = {
      left: candidate.x - candidate.width / 2 - layout.padding,
      right: candidate.x + candidate.width / 2 + layout.padding,
      bottom: candidate.y - layout.offset + layout.padding,
      top: candidate.y - layout.offset - layout.labelHeight - layout.padding,
    };
    if (box.left < 0 || box.top < 0 || box.right > layout.viewWidth || box.bottom > layout.viewHeight) continue;
    if (kept.some((other) => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top)) continue;
    kept.push(box);
    ids.push(candidate.id);
  }
  return ids;
}
