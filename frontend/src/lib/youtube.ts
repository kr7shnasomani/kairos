/** The 11-character video id out of any YouTube URL shape; null for anything else.
 *
 *  This is the switch behind the landing page's demo player: paste a link into
 *  `DEMO_YOUTUBE_URL` (app/page.tsx) and the section appears. A silent null means
 *  it never does, which is why the shapes are pinned by a test.
 */
export function youTubeId(url: string): string | null {
  return url.match(/(?:youtu\.be\/|[?&]v=|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})/)?.[1] ?? null;
}
