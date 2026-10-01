/** Exact public assets produced by the v0.1.0 tag release workflow. */
export const releaseDownloads = [
  { label: 'Linux · Intel / AMD 64 位', name: 'amail-v0.1.0-x86_64-unknown-linux-gnu.tar.gz' },
  { label: 'Linux · ARM 64 位', name: 'amail-v0.1.0-aarch64-unknown-linux-gnu.tar.gz' },
  { label: 'Windows · Intel / AMD 64 位', name: 'amail-v0.1.0-x86_64-pc-windows-msvc.zip' },
  { label: 'macOS · Apple 芯片', name: 'amail-v0.1.0-aarch64-apple-darwin.tar.gz' },
  { label: 'macOS · Intel 芯片', name: 'amail-v0.1.0-x86_64-apple-darwin.tar.gz' },
  { label: 'Agent Skill', name: 'amail-agent-skill-v0.1.0.zip' },
  { label: 'SHA-256 校验清单 · SHA256SUMS', name: 'SHA256SUMS' },
].map((asset) => ({
  ...asset,
  href: `https://github.com/kleedaisuki/moesegfault-amail/releases/download/v0.1.0/${asset.name}`,
}));
