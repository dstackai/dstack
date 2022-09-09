import React, { useState, useEffect, useRef, forwardRef } from 'react';
import cx from 'classnames';
import RcTooltip from 'rc-tooltip';
import { TooltipProps } from 'types/Tooltip';
import { refSetter } from 'libs/refSetter';
import cn from 'classnames';
import css from './index.module.css';
import { stopPropagation } from '../../libs';

interface DropdownItem {
    className?: string;
    children: React.ReactNode | React.ReactElement | string;
    onClick?: () => void;
    disabled?: boolean;
}

interface Props
    extends Omit<
        TooltipProps,
        'overlay' | 'trigger' | 'children' | 'destroyTooltipOnHide' | 'visible' | 'overlayClassName' | 'arrowContent' | 'ref'
    > {
    className?: string;
    items: DropdownItem[];
    children: React.ReactElement;
}

const Dropdown = forwardRef<HTMLSelectElement, Props>(
    ({ className, children, items, placement = 'bottomRight', ...props }, ref) => {
        const [isShow, setIsShow] = useState<boolean>(false);
        const buttonRef = useRef(null);
        const dropdownRef = useRef(null);

        useEffect(() => {
            document.body.addEventListener('click', outsideClickHandle);
            return () => document.body.removeEventListener('click', outsideClickHandle);
        });

        const outsideClickHandle = (event: MouseEvent | TouchEvent) => {
            let targetElement = event.target as HTMLElement;

            do {
                if (targetElement === buttonRef.current || targetElement === dropdownRef.current) return;

                targetElement = targetElement.parentNode as HTMLElement;
            } while (targetElement);

            if (isShow) setIsShow(false);
        };

        const onCLickButton = (event: MouseEvent | TouchEvent) => {
            stopPropagation(event);
            setIsShow(!isShow);
        };

        const clickStopPropagation = (event: React.MouseEvent<HTMLElement>) => {
            const targetElement = event.target as HTMLElement;

            if (targetElement.tagName.toLowerCase() !== 'a') event.preventDefault();
            event.stopPropagation();
        };

        const onCLickItem = (item: DropdownItem) => {
            setIsShow(!isShow);

            if (item.onClick) item.onClick();
        };

        const renderItem = (item: DropdownItem, index?: number) => {
            return (
                <div
                    key={index}
                    className={cn(css.item, item.className, { [css.withClick]: item.onClick, [css.disabled]: item.disabled })}
                    onClick={() => onCLickItem(item)}
                >
                    {item.children}
                </div>
            );
        };

        return (
            <RcTooltip
                overlayClassName={cn(css.wrapper, className)}
                arrowContent={null}
                visible={isShow}
                placement={placement}
                ref={refSetter(ref, dropdownRef)}
                overlay={
                    <div className={cx(css.dropdown)} onClick={clickStopPropagation}>
                        {items.map(renderItem)}
                    </div>
                }
                {...props}
            >
                {React.cloneElement(children, {
                    onClick: onCLickButton,
                    ref: buttonRef,
                })}
            </RcTooltip>
        );
    },
);

export default Dropdown;
