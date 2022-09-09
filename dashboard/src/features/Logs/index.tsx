import React, { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import BaseLogs, { Props as BaseLogsProps } from 'components/details/Logs';
import useAwsLogs from 'hooks/useAwsLogs';
import { useGetUserInfoQuery } from 'services/user';
import { getYesterdayTimeStamp } from 'libs';
import { useAppDispatch } from 'hooks';
import { resetHasLogs, setHasLogs } from './slice';
import css from './index.module.css';
import cn from 'classnames';

export interface Props extends BaseLogsProps, Pick<IRun, 'user_name' | 'run_name'> {}

const Logs: React.FC<Props> = ({ user_name, run_name, ...props }) => {
    const ref = useRef<HTMLDivElement>(null);
    const { data: userInfo } = useGetUserInfoQuery();
    const yesterdayTime = useRef<number>(getYesterdayTimeStamp());

    const dispatch = useAppDispatch();
    const fullName = `${user_name}/${run_name}`;

    const { logs, isLoading } = useAwsLogs(
        ref,
        {
            region: userInfo?.default_configuration?.aws_region ?? '',
            accessKeyId: userInfo?.default_configuration?.aws_access_key_id ?? '',
            secretAccessKey: userInfo?.default_configuration?.aws_secret_access_key ?? '',
            logGroupName: fullName,
            startTime: yesterdayTime.current,
        },
        { pollingInterval: 2000 },
    );

    useEffect(() => {
        if (isLoading) dispatch(resetHasLogs(fullName));
        else dispatch(setHasLogs({ fullName, has: !!logs.length }));
    }, [isLoading, logs]);

    useEffect(() => {
        return () => {
            dispatch(resetHasLogs(fullName));
        };
    }, []);

    // if (!isLoading && !logs.length) return <div className={cn(css.empty, props.className)}>{t('run_logs_empty_message')}</div>;

    return (
        <BaseLogs ref={ref} isLoading={isLoading} {...props}>
            {logs.map((i) => i + '\n')}
        </BaseLogs>
    );
};

export default Logs;
