import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import classNames from 'classnames';
import { Mode } from '@cloudscape-design/global-styles';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';

import { Container, Header, ListEmptyMessage, Loader, TextContent } from 'components';

import { useAppSelector } from 'hooks';
import { useGetProjectLogsQuery } from 'services/project';
import { useGetRunQuery } from 'services/run';

import { selectSystemMode } from 'App/slice';

import { getJobSubmissionId } from './helpers';

import { IProps } from './types';

import styles from './styles.module.scss';

const LIMIT_LOG_ROWS = 1000;

export const Logs: React.FC<IProps> = ({ className, ...props }) => {
    const { t } = useTranslation();
    const params = useParams();
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    const paramProjectName: string = props.name ?? params.projectName ?? '';
    const paramRunName = props.run_name ?? params.runName ?? '';
    const appliedTheme = useAppSelector(selectSystemMode);

    const terminalInstance = useRef<Terminal>(new Terminal());

    const fitAddonInstance = useRef<FitAddon>(new FitAddon());
    const [logsData, setLogsData] = useState<ILogItem[]>([]);

    useEffect(() => {
        if (appliedTheme === Mode.Light) {
            terminalInstance.current.options.theme = {
                foreground: '#000716',
                background: '#ffffff',
            };
        } else {
            terminalInstance.current.options.theme = {
                foreground: '#b6bec9',
                background: '#0f1b2a',
            };
        }
    }, [appliedTheme]);

    useEffect(() => {
        terminalInstance.current.loadAddon(fitAddonInstance.current);

        const onResize = () => {
            fitAddonInstance.current.fit();
        };

        window.addEventListener('resize', onResize);

        return () => {
            window.removeEventListener('resize', onResize);
        };
    }, []);

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        run_name: paramRunName,
    });

    const {
        data: fetchData,
        isLoading: isLoadingLogs,
        isFetching: isFetchingLogs,
    } = useGetProjectLogsQuery(
        {
            project_name: paramProjectName,
            run_name: paramRunName,
            descending: true,
            job_submission_id: getJobSubmissionId(runData) ?? '',
            limit: LIMIT_LOG_ROWS,
        },
        {
            skip: !runData,
        },
    );

    const isLoading = isLoadingRun || isLoadingLogs;

    useEffect(() => {
        if (fetchData) {
            const reversed = [...fetchData].reverse();
            setLogsData((old) => [...reversed, ...old]);
        }
    }, [fetchData]);

    useEffect(() => {
        const element = document.getElementById('terminal');

        if (logsData.length && terminalInstance.current && element) {
            terminalInstance.current.open(element);

            logsData.forEach((logItem) => {
                terminalInstance.current.write(logItem.message);
            });

            fitAddonInstance.current.fit();
        }
    }, [logsData]);

    return (
        <div className={classNames(styles.logs, className)}>
            <Container header={<Header variant="h2">{t('projects.run.log')}</Header>}>
                <TextContent>
                    <Loader padding={'n'} className={classNames(styles.loader, { show: isLoading || isFetchingLogs })} />

                    {!isLoading && !logsData.length && (
                        <ListEmptyMessage
                            title={t('projects.run.log_empty_message_title')}
                            message={t('projects.run.log_empty_message_text')}
                        />
                    )}

                    <div className={styles.terminal} id="terminal" />
                </TextContent>
            </Container>
        </div>
    );
};
