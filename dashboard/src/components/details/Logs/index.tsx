import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    isLoading?: boolean;
}

const Logs = React.forwardRef<HTMLDivElement, Props>(({ children, isLoading, className, ...props }, ref) => {
    return (
        <div ref={ref} className={cn(css.logs, className)} {...props}>
            {children}

            {isLoading && (
                <div className={css.loader}>
                    {new Array(13).fill({}).map((i, index) => (
                        <div className={css.row} key={index} />
                    ))}
                </div>
            )}
        </div>
    );
});

export default Logs;
