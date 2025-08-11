import React, { useEffect, useRef, useState } from 'react';
import cn from 'classnames';

import { Icon } from 'components';

import styles from '../../styles.module.scss';

export const LogRow: React.FC<{
    logItem: ILogItem;
    isShowTimestamp?: boolean;
}> = ({ logItem, isShowTimestamp }) => {
    const [collapsed, setCollapsed] = useState(true);
    const [showChevron, setShowChevron] = useState(true);
    const messageInnerRef = useRef(null);

    const toggleCollapsed = () => setCollapsed((val) => !val);

    useEffect(() => {
        const observeTarget = messageInnerRef.current;
        if (!observeTarget) return;

        const resizeObserver = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry) {
                const { height } = entry.contentRect;

                setShowChevron(height > 32);
            }
        });

        resizeObserver.observe(observeTarget);

        return () => {
            resizeObserver.unobserve(observeTarget);
        };
    }, []);

    return (
        <tr className={styles.logItem}>
            {isShowTimestamp && (
                <td className={styles.timestamp}>
                    <span className={cn(styles.toggleCollapse, { [styles.hidden]: !showChevron })} onClick={toggleCollapsed}>
                        <Icon name={collapsed ? 'caret-right-filled' : 'caret-down-filled'} />
                    </span>{' '}
                    {new Date(logItem.timestamp).toISOString()}
                </td>
            )}
            <td className={styles.messageCol}>
                <div className={cn(styles.message, { [styles.collapsed]: collapsed && isShowTimestamp })}>
                    <div ref={messageInnerRef} className={styles.messageInner}>
                        {logItem.message}
                    </div>
                </div>
            </td>
        </tr>
    );
};
