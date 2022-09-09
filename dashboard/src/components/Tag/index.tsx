import React, { HTMLAttributes } from 'react';
import cn from 'classnames';
import Button from 'components/Button';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import { ReactComponent as TagIcon } from 'assets/icons/tag-outline.svg';
import css from './index.module.css';

export interface Props extends HTMLAttributes<HTMLDivElement> {
    title: string;
    close?: () => void;
    withIcon?: boolean;
}

const Tag: React.FC<Props> = ({ title, className, close, withIcon, onClick, ...props }) => {
    return (
        <div
            className={cn(css.tag, className, { [css.pointer]: onClick, [css.widthClose]: !!close })}
            onClick={onClick}
            {...props}
        >
            {withIcon && <TagIcon className={css.icon} />}
            {title}
            {close && (
                <Button
                    dimension="s"
                    appearance="gray-transparent"
                    displayAsRound
                    icon={<CloseIcon width="12" height="12" />}
                    onClick={close}
                    className={css.close}
                />
            )}
        </div>
    );
};

export default Tag;
