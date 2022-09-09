import React from 'react';
import css from './index.module.css';
import cn from 'classnames';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    variable: {
        key: string;
        value: string;
    };
}

const Variable: React.FC<Props> = ({ variable: { key, value }, className, ...props }) => {
    return <div className={cn(css.variable, className)} {...props}>{`${key}: ${value}`}</div>;
};

export default Variable;
