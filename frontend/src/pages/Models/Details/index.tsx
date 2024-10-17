import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import reactStringReplace from 'react-string-replace';
import cn from 'classnames';
import OpenAI from 'openai';

import {
    Box,
    Button,
    Code,
    ColumnLayout,
    Container,
    ContentLayout,
    DetailsHeader,
    FormTextarea,
    Header,
    ListEmptyMessage,
    Loader,
    Modal,
    NavigateLink,
    SelectCSD,
    SelectCSDProps,
    SpaceBetween,
} from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { copyToClipboard, riseRouterException } from 'libs';
import { getExtendedModelFromRun } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { selectAuthToken } from 'App/slice';
import { runIsStopped } from 'pages/Runs/utils';

import { getCurlModelCode, getPythonModelCode } from './helpers';

import { IModelExtended } from '../List/types';
import { FormValues, Message, Role } from './types';

import { ReactComponent as SourceIcon } from 'assets/icons/source.svg';
import css from './styles.module.scss';

const MESSAGE_ROLE_MAP: Record<Role, string> = {
    tool: 'Tool',
    system: 'System',
    user: 'User',
    assistant: 'Assistant',
};

const VIEW_CODE_TYPE_OPTIONS = [
    { label: 'Python', value: 'python' },
    { label: 'Curl', value: 'curl' },
];

export const ModelDetails: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const [messages, setMessages] = useState<Message[]>([]);
    const [viewCodeVisible, setViewCodeVisible] = useState<boolean>(false);
    const [selectedCode, setSelectedCode] = useState<SelectCSDProps.Option>(VIEW_CODE_TYPE_OPTIONS[0]);
    const [loading, setLoading] = useState<boolean>(false);
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunName = params.runName ?? '';
    const openai = useRef<OpenAI>();
    const textAreaRef = useRef<HTMLDivElement>(null);
    const chatList = useRef<HTMLElement>();
    const [pushNotification] = useNotifications();

    const messageForShowing = useMemo<Message[]>(() => messages.filter((m) => m.role !== 'system'), [messages]);

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.FORMAT(paramProjectName),
        },
        {
            text: t('navigation.models'),
            href: ROUTES.MODELS.LIST,
        },
        {
            text: paramRunName,
            href: ROUTES.MODELS.DETAILS.FORMAT(paramProjectName, paramRunName),
        },
    ]);

    const scrollChatToBottom = () => {
        if (!chatList.current) return;

        const { clientHeight, scrollHeight } = chatList.current;
        chatList.current.scrollTo(0, scrollHeight - clientHeight);
    };

    const { data: runData, isLoading: isLoadingRun } = useGetRunQuery({
        project_name: paramProjectName,
        run_name: paramRunName,
    });

    useEffect(() => {
        if (runData && runIsStopped(runData.status)) {
            riseRouterException();
        }
    }, [runData]);

    const modelData = useMemo<IModelExtended | undefined | null>(() => {
        if (!runData) {
            return;
        }

        return getExtendedModelFromRun(runData);
    }, [runData]);

    useEffect(() => {
        if (!modelData) {
            return;
        }

        openai.current = new OpenAI({
            baseURL: modelData.base_url,
            apiKey: token,
            dangerouslyAllowBrowser: true,
        });
    }, [modelData, token]);

    useEffect(() => {
        scrollChatToBottom();
    }, [messageForShowing]);

    const { handleSubmit, control, setValue, watch } = useForm<FormValues>();

    const messageText = watch('message');

    const sendRequest = async (messages: Message[]) => {
        if (!openai.current) return Promise.reject('Model not found');

        return openai.current.chat.completions.create({
            model: modelData?.name ?? '',
            messages,
            stream: true,
            max_tokens: 512,
        });
    };

    const onSubmit = async (data: FormValues) => {
        if (!data.message) {
            return;
        }

        let newMessages: Message[];

        const newMessage: Message = { role: 'user', content: data.message };
        const messagesWithoutSystemMessage = messages.filter((m) => m.role !== 'system');

        if (data.instructions?.length) {
            newMessages = [{ role: 'system', content: data.instructions }, ...messagesWithoutSystemMessage, newMessage];
        } else {
            newMessages = [...messagesWithoutSystemMessage, newMessage];
        }

        setMessages(newMessages);
        setLoading(true);

        try {
            const stream = await sendRequest(newMessages);

            setMessages((oldMessages) => [
                ...oldMessages,
                {
                    role: 'assistant',
                    content: '',
                },
            ]);

            setValue('message', '');

            for await (const chunk of stream) {
                setMessages((oldMessages) => {
                    const newMessages = [...oldMessages];

                    const lastMessage = newMessages.pop();

                    if (!lastMessage) {
                        return oldMessages;
                    }

                    return [
                        ...newMessages,
                        {
                            role: chunk.choices[0]?.delta?.role ?? lastMessage?.role,
                            content: (lastMessage?.content ?? '') + (chunk.choices[0]?.delta?.content ?? ''),
                        },
                    ];
                });
            }
        } catch (e) {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: e }),
            });

            clearChat();
        }

        setLoading(false);
    };

    const clearChat = () => {
        setValue('message', '');
        setValue('instructions', '');

        setMessages([]);
    };

    const renderMessageBody = (content: Message['content']) => {
        const LANGUAGE_PATTERN = /^(```[A-Za-z]*)/m;
        const PATTERN = /^([A-Za-z \t]*)```([A-Za-z]*)?\n([\s\S]*?)```([A-Za-z \t]*)*$/gm;
        const languages: string[] = [];

        const matches = content.match(LANGUAGE_PATTERN);

        if (matches) {
            [...matches].forEach((l) => l && languages.push(l.replace(/^```/, '')));
        }

        const replacedStrings = reactStringReplace(content, PATTERN, (match) => {
            if (!match) {
                return '';
            }

            return <Code>{match}</Code>;
        });

        return (
            <Box variant="p">
                {replacedStrings.filter((line, index) => {
                    if (
                        languages.includes(line) &&
                        typeof replacedStrings[index + 1] !== 'string' &&
                        typeof replacedStrings[index + 1] !== undefined
                    ) {
                        return false;
                    }

                    return true;
                })}
            </Box>
        );
    };

    const onChangeMessage = () => {
        if (!textAreaRef.current) return;

        const textAreaElement = textAreaRef.current.querySelector('textarea');

        if (!textAreaElement) return;

        textAreaElement.style.height = 'auto';
        textAreaElement.style.height = textAreaElement.scrollHeight + 'px';
    };

    const onKeyDown = (event) => {
        const isCtrlOrShiftKey = event?.detail?.ctrlKey || event?.detail?.shiftKey;

        if (event?.detail?.keyCode === 13 && !isCtrlOrShiftKey) {
            handleSubmit(onSubmit)();
        } else if (event?.detail?.keyCode === 13 && isCtrlOrShiftKey) {
            event.preventDefault();
            setValue('message', messageText + '\n');
            setTimeout(onChangeMessage, 0);
        }
    };

    const pythonCode = getPythonModelCode(modelData);

    const curlCode = getCurlModelCode(modelData);

    const onCopyCode = () => {
        switch (selectedCode.value) {
            case VIEW_CODE_TYPE_OPTIONS[0].value:
                return copyToClipboard(pythonCode);
            case VIEW_CODE_TYPE_OPTIONS[1].value:
                return copyToClipboard(curlCode);
        }
    };

    return (
        <ContentLayout
            header={
                <DetailsHeader
                    title={
                        <NavigateLink href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(paramProjectName, paramRunName)}>
                            <Box variant="h1">{paramRunName}</Box>
                        </NavigateLink>
                    }
                />
            }
        >
            {isLoadingRun && (
                <Container>
                    <Loader />
                </Container>
            )}

            {modelData && (
                <>
                    <div className={css.modelDetailsLayout}>
                        <div className={css.general}>
                            <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                                <ColumnLayout columns={4} variant="text-grid">
                                    <div>
                                        <Box variant="awsui-key-label">{t('models.details.run_name')}</Box>
                                        <div>{modelData.run_name}</div>
                                    </div>

                                    <div>
                                        <Box variant="awsui-key-label">{t('models.model_name')}</Box>
                                        <div>{modelData.name}</div>
                                    </div>

                                    <div>
                                        <Box variant="awsui-key-label">{t('models.type')}</Box>
                                        <div>{modelData.type}</div>
                                    </div>
                                </ColumnLayout>
                            </Container>
                        </div>

                        <form className={css.modelForm} onSubmit={handleSubmit(onSubmit)}>
                            <div className={css.buttons}>
                                <Button iconSvg={<SourceIcon />} disabled={loading} onClick={() => setViewCodeVisible(true)} />

                                <Button iconName="remove" disabled={loading || !messages.length} onClick={clearChat} />
                            </div>

                            <aside className={css.side}>
                                <FormTextarea
                                    rows={4}
                                    disabled={loading}
                                    label={t('models.details.instructions')}
                                    constraintText={t('models.details.instructions_description')}
                                    control={control}
                                    name="instructions"
                                />
                            </aside>

                            <div className={css.chat} ref={chatList}>
                                {!messageForShowing.length && (
                                    <ListEmptyMessage
                                        title={t('models.details.chat_empty_title')}
                                        message={t('models.details.chat_empty_message')}
                                    />
                                )}

                                {messageForShowing.map((message, index) => (
                                    <div key={index} className={cn(css.message, css[message.role])}>
                                        <Box variant="h4">
                                            {MESSAGE_ROLE_MAP[message.role as keyof typeof MESSAGE_ROLE_MAP]}
                                        </Box>
                                        {renderMessageBody(message.content || '...')}
                                    </div>
                                ))}
                            </div>

                            <div ref={textAreaRef} className={css.messageForm}>
                                <FormTextarea
                                    stretch
                                    placeholder={t('models.details.message_placeholder')}
                                    control={control}
                                    disabled={loading}
                                    name="message"
                                    onKeyDown={onKeyDown}
                                    onChange={onChangeMessage}
                                />

                                <div className={css.buttons}>
                                    <Button variant="primary" disabled={loading}>
                                        {t('common.send')}
                                    </Button>
                                </div>
                            </div>
                        </form>
                    </div>

                    <Modal
                        visible={viewCodeVisible}
                        header={t('models.details.view_code')}
                        size="large"
                        footer={
                            <Box float="right">
                                <Button variant="normal" onClick={() => setViewCodeVisible(false)}>
                                    {t('common.close')}
                                </Button>
                            </Box>
                        }
                        onDismiss={() => setViewCodeVisible(false)}
                    >
                        <SpaceBetween size="m" direction="vertical">
                            <Box>{t('models.details.view_code_description')}</Box>

                            <div className={css.viewCodeControls}>
                                <SelectCSD
                                    options={VIEW_CODE_TYPE_OPTIONS}
                                    selectedOption={selectedCode}
                                    expandToViewport={true}
                                    onChange={(event) => {
                                        setSelectedCode(event.detail.selectedOption);
                                    }}
                                />

                                <Button iconName="copy" onClick={onCopyCode}></Button>
                            </div>

                            {selectedCode.value === VIEW_CODE_TYPE_OPTIONS[0].value && <Code>{pythonCode}</Code>}

                            {selectedCode.value === VIEW_CODE_TYPE_OPTIONS[1].value && <Code>{curlCode}</Code>}
                        </SpaceBetween>
                    </Modal>
                </>
            )}
        </ContentLayout>
    );
};
