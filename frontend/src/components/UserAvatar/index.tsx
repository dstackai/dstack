import React from 'react';
import Avatar from 'react-avatar';
import { product } from 'product';

type Props = {
    userName?: string;
    // In pixels
    size: number;
};

/**
 * A user's avatar: their GitHub one in dstack Sky, else their initials.
 */
export const UserAvatar: React.FC<Props> = ({ userName, size }) => {
    const avatarProps = product.isSky ? { githubHandle: userName } : { name: userName };

    return <Avatar {...avatarProps} size={`${size}px`} round />;
};
