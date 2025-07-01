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

        setTimeout(() => {
            textAreaRef.current?.querySelector('textarea')?.focus();
        }, 10);
    };

    const clearChat = () => {
        setValue('message', '');
        setValue('instructions', '');

        setMessages([]);
        setTimeout(onChangeMessage, 10);
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
                        languages.includes(line as string) &&
                        typeof replacedStrings[index + 1] !== 'string' &&
                        typeof replacedStrings[index + 1] !== 'undefined'
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

    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
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

    console.log({ modelData });

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

                                        <div>
                                            <NavigateLink
                                                href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(
                                                    modelData.project_name,
                                                    modelData.run_name ?? 'No run name',
                                                )}
                                            >
                                                {modelData.run_name}
                                            </NavigateLink>
                                        </div>
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
                                    <div key={index} className={css.message}>
                                        <ChatBubble
                                            ariaLabel=""
                                            type={message.role === 'user' ? 'outgoing' : 'incoming'}
                                            avatar={
                                                <Avatar
                                                    ariaLabel={MESSAGE_ROLE_MAP[message.role as keyof typeof MESSAGE_ROLE_MAP]}
                                                    color={message.role === 'user' ? 'default' : 'gen-ai'}
                                                    iconName={message.role === 'user' ? 'user-profile' : 'gen-ai'}
                                                />
                                            }
                                        >
                                            {renderMessageBody(message.content || '...')}
                                        </ChatBubble>
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
