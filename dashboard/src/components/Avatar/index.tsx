import React from 'react';
import ColorHash from 'color-hash';
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
// import { getHash } from 'emoji-hash-gen';
import cn from 'classnames';
import css from './index.module.css';

export enum AvatarSizes {
    'xl' = 246,
    's' = 32,
}

type AvatarAppearance = 'square' | 'round';
type AvatarSize = keyof typeof AvatarSizes;

interface Props {
    onClick?: () => void;
    className?: string;
    name: string;
    size?: AvatarSize;
    appearance?: AvatarAppearance;
}

const colorHash = new ColorHash({ saturation: 1.0 });

export const stringToColour = (s: string): string => colorHash.hex(s);

const generateColours = (s: string): [string, string] => {
    const s1 = s.substring(0, s.length / 2);
    const s2 = s.substring(s.length / 2);
    const c1 = stringToColour(s1);
    const c2 = stringToColour(s2);

    return [c1, c2];
};

const Avatar: React.FC<Props> = ({ className, name, size = 's', appearance = 'round', onClick }) => {
    const [startColor, endColor] = generateColours(name);
    // const emoji = getHash(name, { length: 1 });

    return (
        <div
            className={cn(css.avatar, className, `size-${size}`, `appearance-${appearance}`)}
            onClick={onClick}
            style={{
                width: `${AvatarSizes[size]}px`,
                height: `${AvatarSizes[size]}px`,
                background: `linear-gradient(135deg, ${startColor}, ${endColor})`,
            }}
        >
            {/*{emoji}*/}
        </div>
    );
};

export default Avatar;
