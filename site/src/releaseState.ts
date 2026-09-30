/** The only publication states accepted by the static site build. */
export type ReleaseState = 'candidate' | 'published';

/**
 * Resolve publication state at build time. Missing state is deliberately a
 * candidate, so local and staging builds cannot accidentally claim a release.
 * Only release-gated production workflows may set `published`.
 */
export function parseReleaseState(value: string | undefined): ReleaseState {
  if (value === undefined || value === '') return 'candidate';
  if (value === 'candidate' || value === 'published') return value;
  throw new Error(`Invalid AMAIL_RELEASE_STATE: expected candidate or published`);
}

/** Build-time publication state shared by all three static pages. */
export const releaseState = parseReleaseState(import.meta.env.AMAIL_RELEASE_STATE);
