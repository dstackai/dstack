import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useOutletContext } from 'react-router-dom';
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
    ExpandableSection,
    FormTextarea,
    Header,
    ListEmptyMessage,
    NavigateLink,
    SpaceBetween,
    StatusIndicator,
} from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { ROUTES } from 'routes';

import { selectAuthToken } from 'App/slice';

import { ModelStatus } from '../../components/ModelStatus';
import { addChunkToMessage, getModelUrl, MAX_TOKENS } from '../helpers';

import { IModelExtended } from '../../List/types';
import { FormValues, Message, Role } from '../types';

import css from './styles.module.scss';

const MESSAGE_ROLE_MAP: Record<Role, string> = {
    tool: 'Tool',
    system: 'System',
    user: 'User',
    assistant: 'Assistant',
};

/**
 * The thinking of a reply. It is open while the thinking arrives, and collapses when the answer starts.
 */
const Thinking: React.FC<{ text: string; hasAnswer: boolean }> = ({ text, hasAnswer }) => {
    const { t } = useTranslation();
    const [expanded, setExpanded] = useState(!hasAnswer);

    useEffect(() => {
        if (hasAnswer) {
            setExpanded(false);
        }
    }, [hasAnswer]);

    return (
        <ExpandableSection
            variant="footer"
            headerText={t('models.details.thinking')}
            expanded={expanded}
            onChange={({ detail }) => setExpanded(detail.expanded)}
        >
            <Box variant="p" color="text-body-secondary" fontSize="body-s">
                {text}
            </Box>
        </ExpandableSection>
    );
};

export const ModelDetails: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const model = useOutletContext<IModelExtended>();
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState<boolean>(false);
    const openai = useRef<OpenAI>();
    const textAreaRef = useRef<HTMLDivElement>(null);
    const chatList = useRef<HTMLElement>();
    const [pushNotification] = useNotifications();

    const messageForShowing = useMemo<Message[]>(() => messages.filter((m) => m.role !== 'system'), [messages]);

    // '...' stands for a reply that is on its way, while nothing of it has arrived yet
    const isAwaited = (message: Message, index: number) =>
        loading && index === messageForShowing.length - 1 && !message.content && !message.thinking;

    const modelUrl = getModelUrl(model);

    const scrollChatToBottom = () => {
        if (!chatList.current) return;

        const { clientHeight, scrollHeight } = chatList.current;
        chatList.current.scrollTo(0, scrollHeight - clientHeight);
    };

    useEffect(() => {
        // Without a URL, the client would send the user's token to its default API
        openai.current = modelUrl
            ? new OpenAI({
                  baseURL: modelUrl,
                  apiKey: token,
                  dangerouslyAllowBrowser: true,
              })
            : undefined;
    }, [modelUrl, token]);

    useEffect(() => {
        scrollChatToBottom();
    }, [messageForShowing]);

    const { handleSubmit, control, setValue, watch } = useForm<FormValues>();

    const messageText = watch('message');

    const sendRequest = async (messages: Message[]) => {
        if (!openai.current) return Promise.reject('Model not found');

        return openai.current.chat.completions.create({
            model: model.name,
            // A reply's thinking isn't sent back to the model
            messages: messages.map(({ role, content }) => ({ role, content })),
            stream: true,
            max_tokens: MAX_TOKENS,
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

                    return [...newMessages, addChunkToMessage(lastMessage, chunk)];
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

    return (
        <div className={css.modelDetailsLayout}>
            <div className={css.general}>
                <Container header={<Header variant="h2">{t('common.general')}</Header>}>
                    <ColumnLayout columns={4} variant="text-grid">
                        <div>
                            <Box variant="awsui-key-label">{t('models.model_name')}</Box>
                            <div>{model.name}</div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('models.status')}</Box>

                            <div>
                                <ModelStatus model={model} />
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('models.project')}</Box>

                            <div>
                                <NavigateLink href={ROUTES.PROJECT.DETAILS.FORMAT(model.project_name)}>
                                    {model.project_name}
                                </NavigateLink>
                            </div>
                        </div>

                        <div>
                            <Box variant="awsui-key-label">{t('models.url')}</Box>
                            <div>{modelUrl || '-'}</div>
                        </div>

                        {model.run && (
                            <div>
                                <Box variant="awsui-key-label">{t('models.run')}</Box>

                                <div>
                                    <NavigateLink
                                        href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(model.project_name, model.run.id)}
                                    >
                                        {model.run.run_name}
                                    </NavigateLink>
                                </div>
                            </div>
                        )}
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
                                <SpaceBetween size="xs">
                                    {!!message.thinking && <Thinking text={message.thinking} hasAnswer={!!message.content} />}

                                    {(!!message.content || isAwaited(message, index)) &&
                                        renderMessageBody(message.content || '...')}

                                    {message.finish_reason === 'length' && (
                                        <StatusIndicator type="warning">
                                            {t('models.details.reply_cut', { limit: MAX_TOKENS.toLocaleString() })}
                                        </StatusIndicator>
                                    )}
                                </SpaceBetween>
                            </ChatBubble>
                        </div>
                    ))}
                </div>

                <div ref={textAreaRef} className={css.messageForm}>
                    <FormTextarea
                        stretch
                        placeholder={t('models.details.message_placeholder')}
                        control={control}
                        disabled={loading || !modelUrl}
                        name="message"
                        onKeyDown={onKeyDown}
                        onChange={onChangeMessage}
                    />

                    <div className={css.buttons}>
                        <Button variant="primary" disabled={loading || !modelUrl}>
                            {t('common.send')}
                        </Button>
                    </div>
                </div>
            </form>
        </div>
    );
};
