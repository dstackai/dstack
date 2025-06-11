import React, { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import classNames from 'classnames';
import type { TabsProps } from '@cloudscape-design/components/tabs';
import GeneralTabs from '@cloudscape-design/components/tabs';

import styles from './styles.module.scss';

export interface IProps extends TabsProps {
    className?: string;
    withNavigation?: boolean;
}

export const Tabs: React.FC<IProps> = ({ className, withNavigation, onChange, activeTabId: activeTabIdProp, ...props }) => {
    const navigate = useNavigate();
    const { pathname } = useLocation();

    const hasContent = useMemo(() => {
        return props.tabs.some((tab) => !!tab.content);
    }, [props.tabs]);

    const activeTabId = useMemo<IProps['activeTabId']>(() => {
        if (activeTabIdProp) return activeTabIdProp;

        if (withNavigation) {
            const tab = props.tabs.find((t) => pathname === t.href);
            return tab?.id;
        }
    }, [pathname, activeTabIdProp]);

    const onChangeTab: TabsProps['onChange'] = (event) => {
        if (withNavigation) {
            const { detail } = event;

            navigate(detail.activeTabHref!);
        }

        if (onChange) onChange(event);
    };

    return (
        <div className={classNames(styles.tabs, { [styles.hasContent]: hasContent }, className)}>
            <GeneralTabs {...props} activeTabId={activeTabId} onChange={onChangeTab} />
        </div>
    );
};
