/** Onder deze breedte wordt het bronnenpaneel een bottom sheet (docs/03). */
export const NARROW_VIEWPORT_PX = 768;

export function isNarrowViewport(width: number): boolean {
  return width < NARROW_VIEWPORT_PX;
}
