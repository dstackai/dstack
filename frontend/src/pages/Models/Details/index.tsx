import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import reactStringReplace from 'react-string-replace';
import OpenAI from 'openai';

import {
    Avatar,
    Box,
    Button,
    ChatBubble,
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
    SpaceBetween,
    Tabs,
} from 'components';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { copyToClipboard, riseRouterException } from 'libs';
import { getExtendedModelFromRun } from 'libs/run';
import { ROUTES } from 'routes';
import { useGetRunQuery } from 'services/run';

import { selectAuthToken } from 'App/slice';
import { runIsStopped } from 'pages/Runs/utils';

import { getModelGateway } from '../helpers';
import { getCurlModelCode, getPythonModelCode } from './helpers';

import { IModelExtended } from '../List/types';
import { FormValues, Message, Role } from './types';

import css from './styles.module.scss';

const MESSAGE_ROLE_MAP: Record<Role, string> = {
    tool: 'Tool',
    system: 'System',
    user: 'User',
    assistant: 'Assistant',
};

enum CodeTab {
    Python = 'python',
    Curl = 'curl',
}

export const ModelDetails: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const [messages, setMessages] = useState<Message[]>([]);
    const [viewCodeVisible, setViewCodeVisible] = useState<boolean>(false);
    const [codeTab, setCodeTab] = useState<CodeTab>(CodeTab.Python);
    const [loading, setLoading] = useState<boolean>(false);
    const [isGenerating, setIsGenerating] = useState<boolean>(false);
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramRunName = params.runName ?? '';
    const openai = useRef<OpenAI>();
    const textAreaRef = useRef<HTMLDivElement>(null);
    const chatList = useRef<HTMLDivElement>(null);
    const [pushNotification] = useNotifications();
    const abortControllerRef = useRef<AbortController | null>(null);

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
        id: paramRunName,
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
            baseURL: getModelGateway(modelData.base_url),
            apiKey: token,
            dangerouslyAllowBrowser: true,
        });
    }, [modelData, token]);

    useEffect(() => {
        scrollChatToBottom();
    }, [messageForShowing]);

    const { handleSubmit, control, setValue, watch } = useForm<FormValues>();
    const messageText = watch('message');

    // Map Message[] to OpenAI's expected message format
    const mapMessagesForOpenAI = (messages: Message[]) =>
        messages.map((msg) => {
            if (msg.role === 'tool') {
                if (!msg.tool_call_id) {
                    throw new Error('tool_call_id is required for tool messages');
                }
                return {
                    role: msg.role,
                    content: msg.content,
                    tool_call_id: msg.tool_call_id, // Now always present
                };
            }
            return {
                role: msg.role,
                content: msg.content,
            };
        });

    const sendRequest = async (messages: Message[]) => {
        if (!openai.current) return Promise.reject('Model not found');

        abortControllerRef.current = new AbortController();

        return openai.current.chat.completions.create(
            {
                model: modelData?.name ?? '',
                messages: mapMessagesForOpenAI(messages),
                stream: true,
                max_tokens: 512,
            },
            {
                signal: abortControllerRef.current.signal,
            },
        );
    };

    const handleCancel = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            setIsGenerating(false);
            setLoading(false);
        }
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
        setIsGenerating(true);

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
            setTimeout(onChangeMessage, 0);

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
                            role: (chunk.choices[0]?.delta?.role as Role) ?? lastMessage?.role,
                            content: (lastMessage?.content ?? '') + (chunk.choices[0]?.delta?.content ?? ''),
                        },
                    ];
                });
            }
        } catch (e: any) {
            if (e.name === 'AbortError') {
                pushNotification({
                    type: 'info',
                    content: t('common.cancelled_by_user'),
                });
            } else {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: e }),
                });
                clearChat();
            }
        } finally {
            setLoading(false);
            setIsGenerating(false);
        }
    };

    const clearChat = () => {
        setValue('message', '');
        setValue('instructions', '');
        setMessages([]);
        setTimeout(onChangeMessage, 10);
    };

    const renderMessageBody = (content: Message['content']) => {
        // Ensure content is a string; fallback to '...' if undefined
        const safeContent = content || '...';

        // Match code blocks like ```language\ncode\n```
        const PATTERN = /```(\w+)?\n([\s\S]*?)\n```/g;

        // Replace code blocks with <Code> components
        const replacedStrings = reactStringReplace(safeContent, PATTERN, (match, language, code) => {
            // language might be undefined; default to 'text'
            return <Code language={typeof language === 'string' ? language : 'text'}>{code}</Code>;
        });

        // If replacedStrings is a single string, Box can accept it.
        // If it's an array (mixed strings and JSX), use a fragment or div instead of Box.
        if (typeof replacedStrings === 'string') {
            return <Box variant="p">{replacedStrings}</Box>;
        }
        return <div className={css.messageBody}>{replacedStrings}</div>;
    };

    const onChangeMessage = () => {
        if (!textAreaRef.current) return;

        const textAreaElement = textAreaRef.current.querySelector('textarea');

        if (!textAreaElement) return;

        textAreaElement.style.height = 'auto';
        textAreaElement.style.height = textAreaElement.scrollHeight + 'px';
    };

    // AWS UI CustomEvent handler for FormTextarea
    const onKeyDownAwsui = (event: CustomEvent<{ keyCode: number; key: string; ctrlKey: boolean; shiftKey: boolean }>) => {
        const { key, ctrlKey, shiftKey } = event.detail;
        if (key === 'Enter' && !ctrlKey && !shiftKey) {
            handleSubmit(onSubmit)();
        } else if (key === 'Enter' && (ctrlKey || shiftKey)) {
            event.preventDefault?.();
            setValue('message', messageText + '\n');
            setTimeout(onChangeMessage, 0);
        }
    };

    const pythonCode = getPythonModelCode({ model: modelData, token });
    const curlCode = getCurlModelCode({ model: modelData, token });

    const onCopyCode = () => {
        switch (codeTab) {
            case CodeTab.Python:
                return copyToClipboard(pythonCode);
            case CodeTab.Curl:
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
                    actionButtons={
                        <Button disabled={loading} onClick={() => setViewCodeVisible(true)}>
                            {t('models.code')}
                        </Button>
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
                                <Button iconName="remove" disabled={loading || !messages.length} onClick={clearChat} />
                                {isGenerating && (
                                    <Button iconName="close" variant="normal" onClick={handleCancel} disabled={!isGenerating}>
                                        {t('common.cancel')}
                                    </Button>
                                )}
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

                                {messageForShowing.map((message, index) => {
                                    const isAssistantGenerating =
                                        isGenerating && index === messageForShowing.length - 1 && message.role === 'assistant';

                                    return (
                                        <div key={index} className={css.message}>
                                            <ChatBubble
                                                ariaLabel=""
                                                type={message.role === 'user' ? 'outgoing' : 'incoming'}
                                                avatar={
                                                    <Avatar
                                                        ariaLabel={
                                                            MESSAGE_ROLE_MAP[message.role as keyof typeof MESSAGE_ROLE_MAP]
                                                        }
                                                        color={message.role === 'user' ? 'default' : 'gen-ai'}
                                                        iconName={message.role === 'user' ? 'user-profile' : 'gen-ai'}
                                                    />
                                                }
                                            >
                                                {isAssistantGenerating ? (
                                                    <div className={css.generatingIndicator}>
                                                        <Loader />
                                                        <span>{t('models.generating')}</span>
                                                    </div>
                                                ) : (
                                                    renderMessageBody(message.content || '...')
                                                )}
                                            </ChatBubble>
                                        </div>
                                    );
                                })}
                            </div>

                            <div ref={textAreaRef} className={css.messageForm}>
                                <FormTextarea
                                    stretch
                                    placeholder={t('models.details.message_placeholder')}
                                    control={control}
                                    disabled={loading}
                                    name="message"
                                    onKeyDown={onKeyDownAwsui} // <-- Use the AWS UI compatible handler
                                    onChange={onChangeMessage}
                                />

                                <div className={css.buttons}>
                                    {isGenerating ? (
                                        <Button variant="normal" onClick={handleCancel}>
                                            {t('common.cancel')}
                                        </Button>
                                    ) : (
                                        <Button variant="primary" disabled={loading}>
                                            {t('common.send')}
                                        </Button>
                                    )}
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
                                <div className={css.copyButton}>
                                    <Button iconName="copy" onClick={onCopyCode}></Button>
                                </div>

                                <Tabs
                                    onChange={({ detail }) => setCodeTab(detail.activeTabId as CodeTab)}
                                    activeTabId={codeTab}
                                    tabs={[
                                        {
                                            label: 'python',
                                            id: CodeTab.Python,
                                            content: <Code>{pythonCode}</Code>,
                                        },
                                        {
                                            label: 'curl',
                                            id: CodeTab.Curl,
                                            content: <Code>{curlCode}</Code>,
                                        },
                                    ]}
                                />
                            </div>
                        </SpaceBetween>
                    </Modal>
                </>
            )}
        </ContentLayout>
    );
};
