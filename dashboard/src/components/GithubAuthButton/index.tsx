import React from 'react';
import cn from 'classnames';
import { ReactComponent as GithubCircleIcon } from 'assets/icons/github-circle.svg';
import Button, { ButtonProps } from 'components/Button';
import css from './index.module.css';
import { goToUrl } from '../../libs';

export interface Props extends Omit<ButtonProps, 'onClick' | 'icon'> {
    url: string;
    withIcon?: boolean;
}

const GithubAuthButton: React.FC<Props> = ({ children, className, url, withIcon = true, ...props }) => {
    const onClick = () => goToUrl(url);

    return (
        <Button
            appearance="black-fill"
            dimension="xl"
            className={cn(css.button, className)}
            onClick={onClick}
            {...(withIcon ? { icon: <GithubCircleIcon /> } : undefined)}
            {...props}
        >
            {children}
        </Button>
    );
};

export default GithubAuthButton;
