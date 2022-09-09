import React from 'react';
import cn from 'classnames';
import css from './index.module.css';
import { ReactComponent as SmallLogo } from '../../assets/images/landing/small-logo.svg';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const AuthPage: React.FC<Props> = ({ children, className, ...props }) => {
    return (
        <section className={cn(css.auth, className)} {...props}>
            <div className={css.smallLogo}>
                <SmallLogo width={56} height={56} />
            </div>

            {children}
        </section>
    );
};

type TitleProps = React.HTMLAttributes<HTMLHeadingElement>;

const Title: React.FC<TitleProps> = ({ children, className, ...props }) => {
    return (
        <h1 className={cn(css.title, className)} {...props}>
            {children}
        </h1>
    );
};

interface SimpleTextProps extends React.HTMLAttributes<HTMLDivElement> {
    dimension?: 'm' | 'l';
}

const SimpleText: React.FC<SimpleTextProps> = ({ children, className, dimension = 'm', ...props }) => {
    return (
        <div className={cn(css.simpleText, css[`dimension-${dimension}`], className)} {...props}>
            {children}
        </div>
    );
};

type ButtonContainerProps = React.HTMLAttributes<HTMLDivElement>;

const ButtonsContainer: React.FC<ButtonContainerProps> = ({ children, className, ...props }) => {
    return (
        <div className={cn(css.buttonsContainer, className)} {...props}>
            {children}
        </div>
    );
};

type FieldContainerProps = React.HTMLAttributes<HTMLDivElement>;

const FieldContainer: React.FC<FieldContainerProps> = ({ children, className, ...props }) => {
    return (
        <div className={cn(css.fieldContainer, className)} {...props}>
            {children}
        </div>
    );
};

type DividerProps = React.HTMLAttributes<HTMLDivElement>;

const Divider: React.FC<DividerProps> = ({ children, className, ...props }) => {
    return (
        <div className={cn(css.divider, className)} {...props}>
            {children}
        </div>
    );
};

export default Object.assign(AuthPage, {
    Title,
    SimpleText,
    ButtonsContainer,
    FieldContainer,
    Divider,
});
