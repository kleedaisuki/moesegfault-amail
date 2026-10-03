import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

/** 中文：每个版本独立成文，新增版本只需追加 Markdown 文件。 English: One Markdown file per release makes the changelog append-only and schema-checked. */
const releases = defineCollection({
  loader: glob({ pattern: '*.md', base: './src/content/releases' }),
  schema: z.object({
    version: z.string().regex(/^v\d+\.\d+\.\d+$/),
    date: z.coerce.date(),
    summary: z.string(),
    /** Unpublished entries are excluded from every published-state build. */
    candidateOnly: z.boolean().default(false),
  }),
});

export const collections = { releases };
