import { defineConfig } from 'astro/config';

/** 中文：发布页全部预渲染为静态资源，避免不必要的服务端运行时。 English: Prerender the release site as static assets; no server runtime is needed. */
export default defineConfig({
  site: 'https://amail.moesegfault.dev',
  output: 'static',
  trailingSlash: 'always',
});
