/** The only publication states accepted by the static site build. */
export type ReleaseState = 'candidate' | 'published';

/** Staging version does not change the last published v0.1.0 download contracts. */
export const candidateVersion = 'v0.1.2';

/** Candidate documentation never asserts publication or public sending authority. */
export const candidateServiceNotice = '这是 v0.1.2 staging 候选版本说明，尚未发布，不表示邮件服务或发送已开放。';

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
