/** Tailwind `md` begint bij 768 px. Mobiele sheets horen daar dicht. */
export const DESKTOP_MEDIA_QUERY = "(min-width: 768px)";

export function sheetStaysOpen(open: boolean, isDesktop: boolean): boolean {
  return isDesktop ? false : open;
}
