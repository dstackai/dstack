import React from 'react';
import { useTranslation } from 'react-i18next';

import { StatusIndicator } from 'components';

import { getStatusIconColor, getStatusIconType } from 'libs/run';

import { getImportedModelStatus } from '../../helpers';

import { IModelExtended } from '../../List/types';

type ModelStatusProps = {
    model: IModelExtended;
};

export const ModelStatus: React.FC<ModelStatusProps> = ({ model }) => {
    const { t } = useTranslation();

    if (model.run) {
        const { status, termination_reason, status_message } = model.run;

        return (
            <StatusIndicator
                type={getStatusIconType(status, termination_reason)}
                colorOverride={getStatusIconColor(status, termination_reason, status_message)}
            >
                {status_message}
            </StatusIndicator>
        );
    }

    const status = getImportedModelStatus(model);

    return (
        <StatusIndicator type={status === 'running' ? 'success' : 'stopped'}>
            {t(`projects.run.statuses.${status}`)}
        </StatusIndicator>
    );
};
