import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import classNames from 'classnames';

import { Container, Header, Loader, TextContent } from 'components';

import { useGetProjectLogsQuery } from 'services/project';

import { IProps } from './types';

import styles from './styles.module.scss';

const LIMIT_LOG_ROWS = 100;
const LOADING_SCROLL_GAP = 100;

export const Logs: React.FC<IProps> = ({ name, repo_id, run_name, className }) => {
    const { t } = useTranslation();
    const scrollRef = useRef<HTMLDivElement>(null);
    const scrollPositionByBottom = useRef<number>(0);
    const [logsData, setLogsData] = useState<ILogItem[]>([]);
    const [prevEventId, setPrevEventId] = useState<TRequestLogsParams['prev_event_id']>();
    const [endTime, setEndTime] = useState<TRequestLogsParams['end_time']>();

    const {
        data: fetchData,
        isLoading,
        isFetching,
    } = useGetProjectLogsQuery({
        name,
        repo_id,
        run_name,
        descending: true,
        prev_event_id: prevEventId,
        end_time: endTime,
        limit: LIMIT_LOG_ROWS,
    });

    const saveScrollPositionByBottom = () => {
        if (!scrollRef.current) return;

        const { clientHeight, scrollHeight, scrollTop } = scrollRef.current;
        scrollPositionByBottom.current = scrollHeight - clientHeight - scrollTop;
    };

    const restoreScrollPositionByBottom = () => {
        if (!scrollRef.current) return;

        const { clientHeight, scrollHeight } = scrollRef.current;
        scrollRef.current.scrollTo(0, scrollHeight - clientHeight - scrollPositionByBottom.current);
    };

    useEffect(() => {
        if (fetchData) {
            saveScrollPositionByBottom();
            const reversed = [...fetchData].reverse();
            setLogsData((old) => [...reversed, ...old]);
        }
    }, [fetchData]);

    useLayoutEffect(() => {
        if (!prevEventId && !endTime) {
            scrollToBottom();
        } else {
            restoreScrollPositionByBottom();
        }

        if (logsData.length) checkNeedMoreLoadingData();
    }, [logsData]);

    const checkNeedMoreLoadingData = () => {
        if (!scrollRef.current) return;

        const { clientHeight, scrollHeight } = scrollRef.current;

        if (scrollHeight - clientHeight <= LOADING_SCROLL_GAP) {
            setPrevEventId(logsData[0].event_id);
            setEndTime(logsData[0].timestamp);
        }
    };

    const onScroll = useCallback<EventListener>(
        (event) => {
            const element = event.target as HTMLDivElement;

            if (element.scrollTop <= LOADING_SCROLL_GAP && !isLoading) {
                setPrevEventId(logsData[0].event_id);
                setEndTime(logsData[0].timestamp);
            }
        },
        [isLoading, logsData],
    );

    useEffect(() => {
        if (!scrollRef.current) return;

        scrollRef.current.addEventListener('scroll', onScroll);

        return () => {
            if (scrollRef.current) scrollRef.current.removeEventListener('scroll', onScroll);
        };
    }, [scrollRef.current, onScroll]);

    const scrollToBottom = () => {
        if (!scrollRef.current) return;

        const { clientHeight, scrollHeight } = scrollRef.current;
        scrollRef.current.scrollTo(0, scrollHeight - clientHeight);
    };

    return (
        <div className={classNames(styles.logs, className)}>
            <Container header={<Header variant="h2">{t('projects.run.log')}</Header>}>
                <TextContent>
                    <Loader padding={'n'} className={classNames(styles.loader, { show: isLoading || isFetching })} />

                    <div ref={scrollRef} className={styles.scroll}>
                        <code>
                            {logsData.map((log, index) => (
                                <div key={log.event_id}>{log.log_message}</div>
                            ))}
                        </code>
                    </div>
                </TextContent>
            </Container>
        </div>
    );
};
