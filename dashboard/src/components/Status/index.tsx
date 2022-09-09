import React, { useMemo } from 'react';
import cn from 'classnames';
import { useTranslation } from 'react-i18next';
import AvailabilityIssuesTooltip from 'components/AvailabilityIssuesTooltip';
import Tooltip from 'components/Tooltip';
import css from './index.module.css';

const iconMap: Record<TStatus, string> = {
    queued: '🕗',
    submitted: '🕗',
    stopping: '🕗',
    stopped: '✅',
    aborting: '🕗',
    running: '⏳',
    aborted: '❌',
    failed: '❌',
    done: '✅',
};

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    type: TStatus;
    availabilityIssues?: IAvailabilityIssues[];
    entityType?: 'workflow' | 'job';
}

const Status: React.FC<Props> = ({ type, className, availabilityIssues, entityType = 'workflow', ...props }) => {
    const { t } = useTranslation();
    const hasAvailabilityIssues = useMemo(() => availabilityIssues && !!availabilityIssues.length, [availabilityIssues]);

    return (
        <div className={cn(css.status, className, css[type], { [css.availabilityIssues]: hasAvailabilityIssues })} {...props}>
            {availabilityIssues && !!availabilityIssues.length ? (
                <AvailabilityIssuesTooltip
                    mouseEnterDelay={1}
                    beforeContent={t(`entity_status_tooltip_${type}`, { entity: t(entityType) })}
                    availabilityIssues={availabilityIssues}
                >
                    <span>⚠</span>
                </AvailabilityIssuesTooltip>
            ) : (
                iconMap[type] && (
                    <Tooltip
                        mouseEnterDelay={1}
                        placement="right"
                        overlayContent={<div>{t(`entity_status_tooltip_${type}`, { entity: t(entityType) })}</div>}
                    >
                        <span>{iconMap[type]}</span>
                    </Tooltip>
                )
            )}
        </div>
    );
};

export default Status;
