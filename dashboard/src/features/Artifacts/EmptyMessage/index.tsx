import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const EmptyMessage: React.FC<Props> = ({ className, children, ...props }) => {
    return (
        <div className={cn(css.empty, className)} {...props}>
            {children}
        </div>
    );
};

export default EmptyMessage;
