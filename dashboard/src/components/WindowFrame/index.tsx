import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    contentClassName?: string;
}

const WindowFrame: React.FC<Props> = ({ children, className, contentClassName, ...props }) => {
    return (
        <div className={cn(css.frame, className)} {...props}>
            <svg className="absolute left-0 top-0 w-3/6" viewBox="0 0 100 172" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M0 0H100L47 172H0V0Z" fill="url(#paint0_linear_47_2)"></path>
                <defs>
                    <linearGradient id="paint0_linear_47_2" x1="50" y1="0" x2="50" y2="100" gradientUnits="userSpaceOnUse">
                        <stop stopColor="white" stopOpacity="0.015"></stop>
                        <stop offset="1" stopColor="white" stopOpacity="0"></stop>
                    </linearGradient>
                </defs>
            </svg>
            <div className={css.header}>
                <div className={css.close} />
                <div className={css.minimize} />
                <div className={css.scale} />
            </div>

            <div className={cn(css.content, contentClassName)}>{children}</div>
        </div>
    );
};

export default WindowFrame;
