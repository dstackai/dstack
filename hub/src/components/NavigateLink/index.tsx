import React from 'react';
import Link, { LinkProps } from '@cloudscape-design/components/link';
import { useNavigate } from 'react-router-dom';
export const NavigateLink: React.FC<LinkProps> = ({ onFollow, ...props }) => {
    const navigate = useNavigate();
    const onFollowHandler: LinkProps['onFollow'] = (event) => {
        event.preventDefault();

        if (onFollow) onFollow(event);
        if (event.detail.href) navigate(event.detail.href);
    };

    return <Link {...props} onFollow={onFollowHandler} />;
};
