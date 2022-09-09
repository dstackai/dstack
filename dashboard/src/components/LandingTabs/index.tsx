import React from 'react';
import cn from 'classnames';
import css from './index.module.css';

interface Tab {
    label: string;
    value: string | number;
}

export interface Props {
    appearance?: 'transparent';
    className?: string;
    onChange?: (value: Tab['value']) => void;
    tabs: Tab[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    tabComponent?: React.JSXElementConstructor<any>;
    value?: Tab['value'];
}

const LandingTabs: React.FC<Props> = ({
    className,
    value: currentTabValue,
    tabs,
    appearance = 'transparent',
    onChange,
    tabComponent,
}: Props) => {
    const getOnClickTab = (value: Tab['value']) => () => {
        if (onChange) onChange(value);
    };

    const Component = tabComponent ? tabComponent : 'div';

    return (
        <div className={cn(css.tabs, appearance, className)}>
            <div className={css.tabsContainer}>
                {tabs.map(({ value, label, ...rest }, index) => (
                    <Component
                        {...rest}
                        key={index}
                        className={cn(css.tab, { active: value && value === currentTabValue })}
                        onClick={getOnClickTab(value)}
                    >
                        {label}
                    </Component>
                ))}
            </div>
        </div>
    );
};

export default LandingTabs;
