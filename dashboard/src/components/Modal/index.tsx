import React, { useRef } from 'react';
import cn from 'classnames';
import Button from 'components/Button';
import Portal from 'components/Portal';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import useOnClickOutside from 'hooks/useOnClickOutside';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    show?: boolean;
    close: () => void;
    dimension?: 'xs' | 's' | 'm';
    children?: React.ReactNode;
}

const Modal: React.FC<Props> = ({ dimension = 's', close, className, show = true, children, ...props }) => {
    const modalRef = useRef(null);

    useOnClickOutside(modalRef, () => {
        show && close();
    });

    return (
        <Portal>
            <div className={cn(css.layer, { show })}>
                <div ref={modalRef} className={cn(css.modal, className, `dimension-${dimension}`)} {...props}>
                    <Button
                        dimension="s"
                        appearance="gray-transparent"
                        displayAsRound
                        icon={<CloseIcon width="14" height="14" />}
                        onClick={close}
                        className={css.close}
                    />
                    {children}
                </div>
            </div>
        </Portal>
    );
};

interface TitleProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode;
}

const Title: React.FC<TitleProps> = ({ children, className }) => {
    return <h3 className={cn(css.title, className)}>{children}</h3>;
};

interface ContentProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode;
}

const Content: React.FC<ContentProps> = ({ children, className }) => {
    return <div className={cn(css.content, className)}>{children}</div>;
};

interface ButtonsProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode;
}

const Buttons: React.FC<ButtonsProps> = ({ children, className }) => {
    return <div className={cn(css.buttons, className)}>{children}</div>;
};

export default Object.assign(Modal, {
    Title,
    Content,
    Buttons,
});
