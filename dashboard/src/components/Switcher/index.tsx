import React, { forwardRef } from 'react';
import cn from 'classnames';
import { useIsMounted } from 'hooks';
import { refSetter } from 'libs/refSetter';
import css from './index.module.css';

export type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>;

const Switcher = forwardRef<HTMLInputElement, Props>(({ className, ...rest }, ref) => {
    const isMounted = useIsMounted();
    const inputRef = React.useRef<HTMLInputElement>(null);

    return (
        <div className={cn(css.switcherWrapper, className, { withAnimation: isMounted() })}>
            <input className={cn(css.checkbox)} {...rest} ref={refSetter(ref, inputRef)} type="checkbox" />
            <div className={css.switcher} />
        </div>
    );
});

export default Switcher;
