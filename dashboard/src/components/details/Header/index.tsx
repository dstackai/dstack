import React from 'react';
import cn from 'classnames';
import Button from 'components/Button';
import { ReactComponent as KeyboardBackspaceIcon } from 'assets/icons/keyboard-backspace.svg';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    backClick?: () => void;
    title: string;
    titleClass?: string;
}

const DetailsHeader: React.FC<Props> = ({ backClick, title, titleClass, className, children }) => {
    return (
        <header className={cn(css.header, className)}>
            {backClick && (
                <Button
                    onClick={backClick}
                    displayAsRound
                    className={css.backButton}
                    appearance="gray-transparent"
                    dimension="s"
                    icon={<KeyboardBackspaceIcon />}
                />
            )}

            <div className={cn(css.title, titleClass)}>{title}</div>

            {children}
        </header>
    );
};

export default DetailsHeader;
