// Remembers in this browser whether the tour has been shown, so it starts by
// itself only on a first visit. Storage can be blocked (private windows,
// strict privacy settings); then the tour simply shows on each visit.
// Bump the version when the steps change enough to show everyone again.
const KEY = 'gamemap.tourSeen.v1';

export function hasSeenTour(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

export function markTourSeen(): void {
  try {
    window.localStorage.setItem(KEY, '1');
  } catch {
    // Storage unavailable; nothing to do.
  }
}
