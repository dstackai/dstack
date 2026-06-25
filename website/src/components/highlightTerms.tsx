import { Fragment, ReactNode } from 'react';

// Terms wrapped with the .highlight outline in body copy (never headers or menus — those just
// don't call this). Order matters: longer / compound terms come first so e.g. "dstack Sky" and
// "dstackai/dstack" win over a bare "dstack". Case-sensitive, each bounded by \b so we don't
// match inside larger words (e.g. "uv" won't hit "uvicorn", "pip" won't hit "pipeline").
const TERMS_RE =
  /\bdstackai\/dstack\b|\bdstack Sky\b|\bdstack\b|\bKubernetes\b|\bTenstorrent\b|\bNVIDIA\b|\bSlurm\b|\bAMD\b|\bTPU\b|\buv\b|\bpip\b/g;

function markString(text: string): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  TERMS_RE.lastIndex = 0;
  while ((match = TERMS_RE.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push(
      <span className="highlight" key={match.index}>
        {match[0]}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (parts.length === 0) return text;
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

// Walks a node tree and outlines the known terms inside string leaves. Non-string nodes (e.g.
// <br/>) pass through untouched; element children aren't recursed into. Apply to body copy only.
export function highlightTerms(node: ReactNode): ReactNode {
  if (typeof node === 'string') return markString(node);
  if (Array.isArray(node)) {
    return node.map((child, i) => <Fragment key={i}>{highlightTerms(child)}</Fragment>);
  }
  return node;
}
