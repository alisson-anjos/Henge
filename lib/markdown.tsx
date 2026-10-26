import {Fragment, type ReactNode} from 'react';

/** The small Markdown subset chat models write: paragraphs, headings, nested - / 1. lists, ``` blocks, **bold**,
 * *italic*, `code` and [links](https://…). Builds React elements (never HTML strings), so model text cannot inject markup. */
export default function Markdown({text}: {text: string}) {
  return <div className="markdown">{blocks(text.replace(/\r\n?/g, '\n').split('\n'))}</div>;
}

const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

function blocks(lines: string[]): ReactNode[] {
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {i++; continue;}
    if (line.trimStart().startsWith('```')) {
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].trimStart().startsWith('```'); i++) code.push(lines[i]);
      i++; out.push(<pre key={out.length}><code>{code.join('\n')}</code></pre>); continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {out.push(<strong key={out.length} className="md-heading">{inline(heading[2])}</strong>); i++; continue;}
    if (LIST.test(line)) {
      const start = i, top = line.match(LIST)!, kind = (m: RegExpMatchArray) => /\d/.test(m[2]);
      // A top-level item of the other kind (1. after -) starts a new list.
      const sameList = (l: string) => {const m = l.match(LIST); return !!m && (m[1].length > top[1].length || kind(m) === kind(top));};
      while (i < lines.length && (sameList(lines[i]) || (lines[i].trim() && !LIST.test(lines[i]) && /^\s+/.test(lines[i])) || (!lines[i].trim() && sameList(lines[i + 1] || '')))) i++;
      out.push(<List key={out.length} lines={lines.slice(start, i)}/>); continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !LIST.test(lines[i]) && !/^#{1,4}\s/.test(lines[i]) && !lines[i].trimStart().startsWith('```')) para.push(lines[i++]);
    out.push(<p key={out.length}>{para.map((l, k) => <Fragment key={k}>{k > 0 && <br/>}{inline(l)}</Fragment>)}</p>);
  }
  return out;
}

/** Items at the first line's indentation; deeper lines belong to the item above them (sub-lists, continuations). */
function List({lines}: {lines: string[]}) {
  const first = lines[0].match(LIST)!;
  const indent = first[1].length, ordered = /\d/.test(first[2]);
  const items: {text: string; rest: string[]}[] = [];
  for (const line of lines) {
    const m = line.match(LIST);
    if (m && m[1].length <= indent) items.push({text: m[3], rest: []});
    else if (items.length) items[items.length - 1].rest.push(line.slice(Math.min(indent + 2, line.length - line.trimStart().length)));
  }
  const body = items.map((it, k) => <li key={k}>{inline(it.text)}{blocks(it.rest)}</li>);
  return ordered ? <ol>{body}</ol> : <ul>{body}</ul>;
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0], k = out.length;
    if (m[1]) out.push(<code key={k}>{t.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={k}>{inline(t.slice(2, -2))}</strong>);
    else if (m[3]) out.push(<em key={k}>{inline(t.slice(1, -1))}</em>);
    else {const [, label, href] = t.match(/^\[([^\]]+)\]\((.+)\)$/)!; out.push(<a key={k} href={href} target="_blank" rel="noreferrer">{label}</a>);}
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
