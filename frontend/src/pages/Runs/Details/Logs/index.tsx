import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import classNames from 'classnames';
import { Mode } from '@cloudscape-design/global-styles';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal } from '@xterm/xterm';

import { Container, Header, ListEmptyMessage, Loader, TextContent } from 'components';

import { useAppSelector } from 'hooks';
import { useLazyGetProjectLogsQuery } from 'services/project';

import { selectSystemMode } from 'App/slice';

import { IProps } from './types';

import styles from './styles.module.scss';

const LIMIT_LOG_ROWS = 1000;

export const Logs: React.FC<IProps> = ({ className, projectName, runName, jobSubmissionId }) => {
    const { t } = useTranslation();
    const appliedTheme = useAppSelector(selectSystemMode);

    const terminalInstance = useRef<Terminal>(new Terminal({scrollback: 10000000}));
    const fitAddonInstance = useRef<FitAddon>(new FitAddon());
    const [logsData, setLogsData] = useState<ILogItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    const [getProjectLogs] = useLazyGetProjectLogsQuery();

    const writeDataToTerminal = (logs: ILogItem[]) => {
        logs.forEach((logItem) => {
            terminalInstance.current.write(logItem.message);
        });

        fitAddonInstance.current.fit();
    };

    const getNextLogItems = (nextToken?: string) => {
        setIsLoading(true);

        if (!jobSubmissionId) {
            return;
        }

        getProjectLogs({
            project_name: projectName,
            run_name: runName,
            descending: false,
            job_submission_id: jobSubmissionId ?? '',
            next_token: nextToken,
            limit: LIMIT_LOG_ROWS,
        })
            .unwrap()
            .then((response) => {
                setLogsData((old) => [...old, ...response.logs]);

                writeDataToTerminal(response.logs);

                if (response.next_token) {
                    getNextLogItems(response.next_token);
                } else {
                    setIsLoading(false);
                }
            })
            .catch(() => setIsLoading(false));
    };

    useEffect(() => {
        if (appliedTheme === Mode.Light) {
            terminalInstance.current.options.theme = {
                foreground: '#000716',
                background: '#ffffff',
                selectionBackground: '#B4D5FE',
            };
        } else {
            terminalInstance.current.options.theme = {
                foreground: '#b6bec9',
                background: '#161d26',
            };
        }
    }, [appliedTheme]);

    useEffect(() => {
        terminalInstance.current.loadAddon(fitAddonInstance.current);

        getNextLogItems();

        const onResize = () => {
            fitAddonInstance.current.fit();
        };

        window.addEventListener('resize', onResize);

        return () => {
            window.removeEventListener('resize', onResize);
        };
    }, []);

    useEffect(() => {
        const element = document.getElementById('terminal');

        if (terminalInstance.current && element) {
            terminalInstance.current.open(element);
        }
    }, []);

    return (
        <div className={classNames(styles.logs, className)}>
            <Container
                header={
                    <Header variant="h2">
                        <div className={styles.headerContainer}>
                            {t('projects.run.log')}
                            <Loader show={isLoading} padding={'n'} className={classNames(styles.loader)} loadingText={''} />
                        </div>
                    </Header>
                }
            >
                <TextContent>
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
