// @flow
import React from 'react';
import RcTooltip from 'rc-tooltip';
import { TooltipProps } from 'types/Tooltip';
import css from './index.module.css';

export interface Props extends Omit<TooltipProps, 'overlay'> {
    className?: string;
    overlayContent?: React.ReactNode;
}

const Tooltip: React.FC<Props> = ({
    children,
    overlayContent,
    arrowContent = null,
    placement = 'bottomLeft',
    trigger = ['hover'],
    overlayStyle,
    ...props
}) => {
    return (
        <RcTooltip
            overlayClassName={css.wrapper}
            overlayStyle={{ pointerEvents: 'none', ...overlayStyle }}
            arrowContent={arrowContent}
            placement={placement}
            trigger={trigger}
            overlay={<div className={css.tooltip}>{overlayContent}</div>}
            {...props}
        >
            {children}
        </RcTooltip>
    );
};

export default Tooltip;
