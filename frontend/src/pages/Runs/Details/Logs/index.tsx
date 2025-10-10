import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import classNames from 'classnames';

import { Box, Button, Code, Container, Header, ListEmptyMessage, Loader, TextContent } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';
import { useLazyGetProjectLogsQuery } from 'services/project';
import { useGetRunQuery } from 'services/run';

import { LogRow } from './components/LogRow';
import { decodeLogs, getJobSubmissionId } from './helpers';

import { IProps } from './types';

import styles from './styles.module.scss';

const LIMIT_LOG_ROWS = 100;
const LOADING_SCROLL_GAP = 300;

export const Logs: React.FC<IProps> = ({ className, projectName, runName, jobSubmissionId }) => {
    const { t } = useTranslation();
    const codeRef = useRef<HTMLDivElement>(null);
    const nextTokenRef = useRef<string | undefined>(undefined);
    const scrollPositionByBottom = useRef<number>(0);

    const [logsData, setLogsData] = useState<ILogItem[]>([]);
    const [externalLink, setExternalLink] = useState<string | undefined>();
    const [isLoading, setIsLoading] = useState(false);
    const [getProjectLogs] = useLazyGetProjectLogsQuery();
    const [isEnabledDecoding, setIsEnabledDecoding] = useLocalStorageState('enable-encode-logs', false);
    const [isShowTimestamp, setIsShowTimestamp] = useLocalStorageState('enable-showing-timestamp-logs', false);

    const logsForView = useMemo(() => {
        if (isEnabledDecoding) {
            return decodeLogs(logsData);
        }

        return logsData;
    }, [logsData, isEnabledDecoding]);

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
            getNextLogItems();
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

                if (nextToken) {
                    setLogsData((old) => [...reversed, ...old]);
                } else {
                    setLogsData(reversed);
                    setExternalLink(response.external_url);
                }

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

    const toggleDecodeLogs = () => {
        saveScrollPositionByBottom();
        setIsEnabledDecoding(!isEnabledDecoding);
    };

    const toggleShowingTimestamp = () => {
        setIsShowTimestamp(!isShowTimestamp);
    };

    useEffect(() => {
        getLogItems();
    }, []);

    useLayoutEffect(() => {
        if (logsForView.length && logsForView.length <= LIMIT_LOG_ROWS) {
            scrollToBottom();
        } else {
            restoreScrollPositionByBottom();
        }

        if (logsForView.length) checkNeedMoreLoadingData();
    }, [logsForView]);

    const onScroll = useCallback<EventListener>(
        (event) => {
            const element = event.target as HTMLDivElement;

            if (element.scrollTop <= LOADING_SCROLL_GAP && !isLoading) {
                getNextLogItems();
            }
        },
        [isLoading, logsForView],
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
                    <div className={styles.headerContainer}>
                        <div className={styles.headerTitle}>
                            <Header variant="h2">{t('projects.run.log')}</Header>
                        </div>

                        {externalLink && (
                            <Button target="_blank" formAction="none" iconName="external" href={externalLink} variant="icon" />
                        )}

                        <Loader
                            show={isLoading && Boolean(logsForView.length)}
                            padding={'n'}
                            className={styles.loader}
                            loadingText={''}
                        />

                        <div className={styles.switchers}>
                            <Box>
                                <Button
                                    ariaLabel="Legacy mode"
                                    formAction="none"
                                    iconName="gen-ai"
                                    variant={isEnabledDecoding ? 'primary' : 'icon'}
                                    onClick={toggleDecodeLogs}
                                />
                            </Box>

                            <Box>
                                <Button
                                    ariaLabel="Show timestamp"
                                    formAction="none"
                                    iconName="status-pending"
                                    variant={isShowTimestamp ? 'primary' : 'icon'}
                                    onClick={toggleShowingTimestamp}
                                />
                            </Box>
                        </div>
                    </div>
                }
            >
                <TextContent>
                    {!isLoading && !logsForView.length && (
                        <ListEmptyMessage
                            title={t('projects.run.log_empty_message_title')}
                            message={t('projects.run.log_empty_message_text')}
                        />
                    )}

                    {!logsForView.length && <Loader show={isLoading} className={styles.mainLoader} />}

                    {Boolean(logsForView.length) && (
                        <Code className={styles.terminal} ref={codeRef}>
                            <table>
                                <tbody>
                                    {logsForView.map((log, i) => (
                                        <LogRow logItem={log} key={i} isShowTimestamp={isShowTimestamp} />
                                    ))}
                                </tbody>
                            </table>
                        </Code>
                    )}
                </TextContent>
            </Container>
        </div>
    );
};

const getJobSubmissionIdFromJobData = (job?: IJob): string | undefined => {
    if (!job) return;

    return job.job_submissions[job.job_submissions.length - 1]?.id;
};

export const JobLogs = () => {
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunId = params.runId ?? '';
    const paramJobName = params.jobName ?? '';

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        id: paramRunId,
    });

    const jobData = useMemo<IJob | null>(() => {
        if (!runData) return null;

        return runData.jobs.find((job) => job.job_spec.job_name === paramJobName) ?? null;
    }, [runData]);

    if (isLoadingRun)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <Logs
            projectName={paramProjectName}
            runName={runData?.run_spec?.run_name ?? ''}
            jobSubmissionId={jobData ? getJobSubmissionIdFromJobData(jobData) : getJobSubmissionId(runData)}
            className={styles.logsPage}
        />
    );
};
