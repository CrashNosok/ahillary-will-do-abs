/** Лёгкий рендер markdown без внешних зависимостей: `##` → подзаголовок, `- `/`* ` → пункт
 *  списка, иначе абзац. Инлайн-токены `[study-id]` (если id есть в citationIds) превращаются
 *  в ссылку-якорь к списку источников (#cit-<id>). Достаточно для формы, что отдаёт модель.
 *
 *  ponytail: свой мини-рендер, а не react-markdown — в репо нет markdown-зависимости, а формат
 *  узкий. SportDetailPage держит свой AdviceMarkdown (без линковки цитат); общий вынос — если
 *  понадобится третьему месту. */

import { Fragment, type ReactNode } from 'react';

const CITE_RE = /\[([^\]\s]+)\]/g;

/** Разбить строку на текст и ссылки-цитаты [id] (только для известных id). */
function renderInline(text: string, citationIds?: Set<string>): ReactNode {
  if (!citationIds || citationIds.size === 0) return text;
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(CITE_RE)) {
    const id = m[1];
    if (!citationIds.has(id)) continue;
    const at = m.index ?? 0;
    if (at > last) out.push(<Fragment key={key++}>{text.slice(last, at)}</Fragment>);
    out.push(
      <a
        key={key++}
        href={`#cit-${id}`}
        className="text-accent no-underline transition-colors hover:underline"
      >
        [{id}]
      </a>,
    );
    last = at + m[0].length;
  }
  if (out.length === 0) return text;
  if (last < text.length) out.push(<Fragment key={key++}>{text.slice(last)}</Fragment>);
  return out;
}

export default function Markdown({
  text,
  citationIds,
}: {
  text: string;
  citationIds?: Set<string>;
}) {
  const lines = text.split('\n');
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="ml-4 list-disc space-y-1 text-muted">
          {list.map((it, i) => (
            <li key={i}>{renderInline(it, citationIds)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (line.startsWith('##')) {
      flush();
      blocks.push(
        <h3 key={`h-${blocks.length}`} className="mt-2 font-display text-lg font-semibold text-fg">
          {line.replace(/^#+\s*/, '')}
        </h3>,
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      list.push(line.slice(2));
    } else {
      flush();
      blocks.push(
        <p key={`p-${blocks.length}`} className="leading-relaxed text-muted">
          {renderInline(line, citationIds)}
        </p>,
      );
    }
  }
  flush();
  return <div className="flex flex-col gap-3">{blocks}</div>;
}
