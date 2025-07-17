import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import classNames from 'classnames';

import { Code, Container, Header, ListEmptyMessage, Loader, TextContent } from 'components';

import { useLazyGetProjectLogsQuery } from 'services/project';

import { decodeLogs } from './helpers';

import { IProps } from './types';

import styles from './styles.module.scss';

const LIMIT_LOG_ROWS = 1000;
const LOADING_SCROLL_GAP = 300;

export const Logs: React.FC<IProps> = ({ className, projectName, runName, jobSubmissionId }) => {
    const { t } = useTranslation();
    const codeRef = useRef<HTMLDivElement>(null);
    const nextTokenRef = useRef<string | undefined>(undefined);
    const scrollPositionByBottom = useRef<number>(0);

    const [logsData, setLogsData] = useState<ILogItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [getProjectLogs] = useLazyGetProjectLogsQuery();

    const saveScrollPositionByBottom = () => {
        if (!codeRef.current) return;

        const { clientHeight, scrollHeight, scrollTop } = codeRef.current;
        scrollPositionByBottom.current = scrollHeight - clientHeight - scrollTop;
    };

    const restoreScrollPositionByBottom = () => {
        if (!codeRef.current) return;

        const { clientHeight, scrollHeight } = codeRef.current;
        codeRef.current.scrollTo(0, scrollHeight - clientHeight - scrollPositionByBottom.current);
    };

    const checkNeedMoreLoadingData = () => {
        if (!codeRef.current) return;

        const { clientHeight, scrollHeight } = codeRef.current;

        if (scrollHeight - clientHeight <= LOADING_SCROLL_GAP) {
            getLogItems();
        }
    };

    const getLogItems = (nextToken?: string) => {
        setIsLoading(true);

        if (!jobSubmissionId) {
            return;
        }

        getProjectLogs({
            project_name: projectName,
            run_name: runName,
            descending: true,
            job_submission_id: jobSubmissionId,
            next_token: nextToken,
            limit: LIMIT_LOG_ROWS,
        })
            .unwrap()
            .then((response) => {
                saveScrollPositionByBottom();
                const reversed = response.logs.toReversed();
                setLogsData((old) => [...decodeLogs(reversed), ...old]);
                nextTokenRef.current = response.next_token;
                setIsLoading(false);
            })
            .catch(() => setIsLoading(false));
    };

    const getNextLogItems = () => {
        if (nextTokenRef.current) {
            getLogItems(nextTokenRef.current);
        }
    };

    useEffect(() => {
        getLogItems();
    }, []);

    useLayoutEffect(() => {
        if (logsData.length && logsData.length <= LIMIT_LOG_ROWS) {
            scrollToBottom();
        } else {
            restoreScrollPositionByBottom();
        }

        if (logsData.length) checkNeedMoreLoadingData();
    }, [logsData]);

    const onScroll = useCallback<EventListener>(
        (event) => {
            const element = event.target as HTMLDivElement;

            if (element.scrollTop <= LOADING_SCROLL_GAP && !isLoading) {
                getNextLogItems();
            }
        },
        [isLoading, logsData],
    );

    useEffect(() => {
        if (!codeRef.current) return;

        codeRef.current.addEventListener('scroll', onScroll);

        return () => {
            if (codeRef.current) codeRef.current.removeEventListener('scroll', onScroll);
        };
    }, [codeRef.current, onScroll]);

    const scrollToBottom = () => {
        if (!codeRef.current) return;

        const { clientHeight, scrollHeight } = codeRef.current;
        codeRef.current.scrollTo(0, scrollHeight - clientHeight);
    };

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

                    <Code className={styles.terminal} ref={codeRef}>
                        {logsData.map((log, i) => (
                            <p key={i}>{log.message}</p>
                        ))}
                    </Code>
                </TextContent>
            </Container>
        </div>
    );
};
