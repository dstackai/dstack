import React from 'react';
import { format } from 'date-fns';
import Tooltip, { Props as TooltipProps } from './Tooltip';
import { useTranslation } from 'react-i18next';

export interface Props extends TooltipProps {
    children: React.ReactElement;
    beforeContent?: React.ReactElement;
    availabilityIssues: IAvailabilityIssues[];
}

const AvailabilityIssuesTooltip: React.FC<Props> = ({ children, beforeContent, availabilityIssues, ...props }) => {
    const { t } = useTranslation();

    return (
        <Tooltip
            placement="right"
            overlayContent={
                <>
                    {beforeContent && (
                        <div>
                            {beforeContent} <br />
                            <br />
                        </div>
                    )}

                    <div>
                        {availabilityIssues.map((item, index) =>
                            item.timestamp ? (
                                <div key={index}>
                                    {t('availability_issues_at_with_time', {
                                        time: format(new Date(item.timestamp), 'dd.MM.yyyy HH:mm'),
                                    })}

                                    {item.message && (
                                        <React.Fragment>
                                            <br />
                                            {item.message}
                                        </React.Fragment>
                                    )}
                                </div>
                            ) : null,
                        )}
                    </div>
                </>
            }
            {...props}
        >
            {children}
        </Tooltip>
    );
};

export default AvailabilityIssuesTooltip;
