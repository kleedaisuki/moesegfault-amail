/** Current release coordinates; published links require the gated published build. */
export const releaseVersion = 'v0.2.0';
export const releaseTagUrl = `https://github.com/kleedaisuki/moesegfault-amail/releases/tag/${releaseVersion}`;

/** Exact public assets produced by the current tag release workflow. */
export const releaseDownloads = [
  { label: 'Linux · Intel / AMD 64 位', name: `amail-${releaseVersion}-x86_64-unknown-linux-gnu.tar.gz` },
  { label: 'Linux · ARM 64 位', name: `amail-${releaseVersion}-aarch64-unknown-linux-gnu.tar.gz` },
  { label: 'Windows · Intel / AMD 64 位', name: `amail-${releaseVersion}-x86_64-pc-windows-msvc.zip` },
  { label: 'macOS · Apple 芯片', name: `amail-${releaseVersion}-aarch64-apple-darwin.tar.gz` },
  { label: 'macOS · Intel 芯片', name: `amail-${releaseVersion}-x86_64-apple-darwin.tar.gz` },
  { label: 'Agent Skill', name: `amail-agent-skill-${releaseVersion}.zip` },
  { label: 'SHA-256 校验清单 · SHA256SUMS', name: 'SHA256SUMS' },
].map((asset) => ({
  ...asset,
  href: `https://github.com/kleedaisuki/moesegfault-amail/releases/download/${releaseVersion}/${asset.name}`,
}));
