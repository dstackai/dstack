import { ReactNode } from 'react';
import { ThemedImage } from '../data/images';

// In-content diagram: a plain string renders a single image, a themed pair swaps with the theme.
function ThemedDocImage({ image }: { image: string | ThemedImage }) {
  if (typeof image === 'string') {
    return <img src={image} alt="" />;
  }

  return (
    <>
      <img src={image.light} alt="" className="doc-diagram doc-diagram--light" />
      <img src={image.dark} alt="" className="doc-diagram doc-diagram--dark" />
    </>
  );
}

// A documentation block with a visual on one side and copy on the other. Pass either
// `image` (rendered via ThemedDocImage) or an arbitrary `visual` node. `imageFirst`
// places the visual on the left, otherwise it sits on the right.
export function AlternatingDocBlock({
  image,
  visual,
  title,
  children,
  action,
  imageFirst = false,
}: {
  image?: string | ThemedImage;
  visual?: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
  imageFirst?: boolean;
}) {
  return (
    <div className={`doc-alternating ${imageFirst ? 'image-first' : ''}`}>
      <div className="doc-visual">{visual ?? (image && <ThemedDocImage image={image} />)}</div>
      <div>
        <h2>{title}</h2>
        <p>{children}</p>
        {action && <div className="doc-action">{action}</div>}
      </div>
    </div>
  );
}
