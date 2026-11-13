import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MapGame } from '../services/gameService';

/** SC 1: time between scan picks. */
export const SCAN_INTERVAL_MS = 5000;

export interface ScanState {
  running: boolean;
  /** The genre filter the scan follows, or null for every game. */
  genre: string | null;
  /** Games the scan can pick from with the current genre. */
  poolSize: number;
  /** The game the scan picked last, or null before the first pick. */
  current: MapGame | null;
  /** Goes up by one on every pick; restarts the countdown bar. */
  step: number;
  start(): void;
  stop(): void;
  /** Pick the next game now and restart the 5 s timer. */
  skip(): void;
}

/**
 * SC 1: picks a random game every 5 seconds and hands it to `onPick`
 * until stopped. With the genre filter (GV 1) on, it only picks games in
 * that genre. It never picks the same game twice in a row.
 */
export function useScan(
  games: MapGame[] | null,
  genre: string | null,
  onPick: (game: MapGame) => void,
): ScanState {
  const [running, setRunning] = useState(false);
  const [current, setCurrent] = useState<MapGame | null>(null);
  const [step, setStep] = useState(0);
  const onPickRef = useRef(onPick);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  const pool = useMemo(
    () => (genre ? (games ?? []).filter((game) => game.genres.includes(genre)) : games ?? []),
    [games, genre],
  );

  const pickNext = useCallback(() => {
    if (pool.length === 0) {
      setRunning(false);
      return;
    }
    let index = Math.floor(Math.random() * pool.length);
    if (pool.length > 1 && pool[index].id === current?.id) index = (index + 1) % pool.length;
    const game = pool[index];
    setCurrent(game);
    setStep((value) => value + 1);
    onPickRef.current(game);
  }, [pool, current]);

  // One timeout per pick: a new pick (step) restarts the 5 s wait.
  useEffect(() => {
    if (!running) return;
    const timer = window.setTimeout(pickNext, SCAN_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [running, step, pickNext]);

  const start = useCallback(() => {
    if (pool.length === 0) return;
    setRunning(true);
    pickNext();
  }, [pool, pickNext]);

  const stop = useCallback(() => setRunning(false), []);

  return {
    running,
    genre,
    poolSize: pool.length,
    current,
    step,
    start,
    stop,
    skip: pickNext,
  };
}
