import React from 'react';
import { useNavigate } from 'react-router-dom';
import Link, { LinkProps } from '@cloudscape-design/components/link';

import styles from './style.module.scss';

export const NavigateLink: React.FC<LinkProps> = ({ onFollow, ...props }) => {
    const navigate = useNavigate();
    const onFollowHandler: LinkProps['onFollow'] = (event) => {
        event.preventDefault();

        if (onFollow) onFollow(event);
        if (event.detail.href) navigate(event.detail.href);
    };

    return (
        <span className={styles.link}>
            <Link {...props} onFollow={onFollowHandler} />
        </span>
    );
};
