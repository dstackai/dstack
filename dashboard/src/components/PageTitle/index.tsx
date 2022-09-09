import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

type Size = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';

export interface Props {
    className?: string;
    variant?: Size;
    children: string | React.ReactNode;
}

const PageTitle: React.FC<Props> = ({ variant = 'h1', className, children }) => {
    const Tag = variant as keyof JSX.IntrinsicElements;

    return <Tag className={cn(css.title, css[variant], className)}>{children}</Tag>;
};

export default PageTitle;
