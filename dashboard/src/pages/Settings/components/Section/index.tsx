import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    disabled?: boolean;
}

const Section: React.FC<Props> = ({ className, disabled, children, ...props }) => {
    return (
        <section className={cn(css.section, className, { disabled })} {...props}>
            {children}
        </section>
    );
};

export type TitleProps = React.HTMLAttributes<HTMLDivElement>;

const Title: React.FC<TitleProps> = ({ className, children, ...props }) => {
    return (
        <div className={cn(css.title, className)} {...props}>
            {children}
        </div>
    );
};

export interface TextProps extends React.HTMLAttributes<HTMLDivElement> {
    strong?: boolean;
}

const Text: React.FC<TextProps> = ({ className, strong, children, ...props }) => {
    return (
        <div className={cn(css.text, className, { [css.strong]: strong })} {...props}>
            {children}
        </div>
    );
};

export default Object.assign(Section, {
    Title,
    Text,
});
