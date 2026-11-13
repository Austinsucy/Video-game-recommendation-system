/** An empty genre means "All genres". No nodes are removed from the map. */
export function matchesGenre(game: { genres: readonly string[] }, selectedGenre: string): boolean {
  return selectedGenre === '' || game.genres.includes(selectedGenre);
}