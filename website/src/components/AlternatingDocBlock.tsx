import { ReactNode } from 'react';
import { highlightTerms } from './highlightTerms';

export function AlternatingDocBlock({
  visual,
  title,
  children,
  action,
  imageFirst = false,
}: {
  visual: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
  imageFirst?: boolean;
}) {
  return (
    <div className={`doc-alternating ${imageFirst ? 'image-first' : ''}`}>
      <div className="doc-visual">{visual}</div>
      <div>
        <h2>{title}</h2>
        <p>{highlightTerms(children)}</p>
        {action && <div className="doc-action">{action}</div>}
      </div>
    </div>
  );
}
