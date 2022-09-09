import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    title?: string;
    description?: string;
}

const EmptyMessage: React.FC<Props> = ({ className, title, description, ...props }) => {
    return (
        <div className={cn(css.empty, className)} {...props}>
            {title && <div className={css.title}>{title}</div>}
            {description && <div className={css.text}>{description}</div>}
        </div>
    );
};

export default EmptyMessage;
