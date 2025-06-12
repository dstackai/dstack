import React, { useRef } from 'react';

import { Box, Icon, Popover, StatusIndicator } from 'components';

import { getRunStatusMessage, getStatusIconColor, getStatusIconType } from 'libs/run';

import { finishedRunStatuses } from '../../constants';

import styles from './styles.module.scss';

type RunStatusIndicatorProps = {
    run: IRun;
};

export const RunStatusIndicator: React.FC<RunStatusIndicatorProps> = ({ run }) => {
    const buttonRef = useRef<HTMLButtonElement>(null);
    const status = finishedRunStatuses.includes(run.status) ? run.latest_job_submission?.status ?? run.status : run.status;

    const terminationReason = finishedRunStatuses.includes(run.status) ? run.latest_job_submission?.termination_reason : null;

    const isShowInfo = ['no offers', 'error'].includes(run.latest_job_submission?.status_message ?? '');

    return (
        <div className={styles.runStatus}>
            <StatusIndicator
                type={getStatusIconType(status, terminationReason)}
                colorOverride={getStatusIconColor(status, terminationReason)}
            >
                {getRunStatusMessage(run)}
            </StatusIndicator>

            {isShowInfo && (
                <div
                    className={styles.infoIcon}
                    onMouseEnter={() => buttonRef.current?.click()}
                    onMouseLeave={() => document.dispatchEvent(new MouseEvent('mousedown'))}
                >
                    <Icon name="status-info" />

                    <Popover
                        dismissButton={false}
                        position="top"
                        size="medium"
                        triggerType="custom"
                        content={<Box>Type your text here</Box>}
                    >
                        <button ref={buttonRef} style={{ display: 'none' }} aria-hidden="true" />
                    </Popover>
                </div>
            )}
        </div>
    );
};
