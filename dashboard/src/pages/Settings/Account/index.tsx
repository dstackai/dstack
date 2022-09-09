import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import Button from 'components/Button';
import CodeViewer from 'components/CodeViewer';
import InputField from 'components/form/InputField';
import TableContentSkeleton from 'components/TableContentSkeleton';
import SettingsSection from 'pages/Settings/components/Section';
import { ReactComponent as CopyIcon } from 'assets/icons/content-copy.svg';
import { copyToClipboard } from 'libs';
import { useGetUserInfoQuery } from 'services/user';
import { useNotifications } from 'hooks';
import css from './index.module.css';

const showVisibility = false;

const cliCode = (token: string) => {
    return `pip install dstack -U
dstack config --token ${token}
`;
};

const Account: React.FC = () => {
    const { t } = useTranslation();
    const { data, isLoading } = useGetUserInfoQuery();
    const [searchParams, setSearchParams] = useSearchParams();
    const message = searchParams.get('message');
    const { push: pushNotification, removeAll: removeAllNotifications } = useNotifications();

    useEffect(() => {
        if (message) {
            pushNotification({
                message,
                type: 'success',
            });

            setSearchParams('');
        }

        return () => removeAllNotifications();
    }, []);

    if (!data || isLoading) return <TableContentSkeleton />;

    return (
        <div>
            <SettingsSection>
                <SettingsSection.Title>{t('profile')}</SettingsSection.Title>

                <div className={css.fields}>
                    <InputField className={css.field} label={t('username')} disabled value={data.user_name} />
                    <InputField className={css.field} label={t('email')} disabled value={data.email} />
                </div>
            </SettingsSection>

            <SettingsSection>
                <SettingsSection.Title>{t('token')}</SettingsSection.Title>
                <SettingsSection.Text className={css.token} strong>
                    {data.token}

                    <Button
                        dimension="s"
                        appearance="gray-transparent"
                        icon={<CopyIcon />}
                        onClick={() => copyToClipboard(data.token)}
                    />
                </SettingsSection.Text>

                {/*<div className={css.supMessage}>*/}
                {/*    <Trans key={'you_can_change_token'}>*/}
                {/*        If you want no longer provide access to dstack.ai for others you can{' '}*/}
                {/*        <a href="#" className="disabled">*/}
                {/*            change the token*/}
                {/*        </a>*/}
                {/*        .*/}
                {/*    </Trans>*/}
                {/*</div>*/}
            </SettingsSection>

            {showVisibility && (
                <SettingsSection>
                    <SettingsSection.Title>{t('visibility')}</SettingsSection.Title>
                    <SettingsSection.Text strong>{t('private')}</SettingsSection.Text>

                    <div className={css.supMessage}>
                        {t('it_means_can_see_your_runs_and_jobs_with_type', { type: t('nobody').toLowerCase() })}{' '}
                        <a href="#" className="disabled">
                            {t('make_it_with_type', { type: t('public').toLowerCase() })}
                        </a>
                    </div>
                </SettingsSection>
            )}

            <SettingsSection>
                <SettingsSection.Title>{t('cli')}</SettingsSection.Title>
                <SettingsSection.Text>{t('cli_text')}</SettingsSection.Text>

                <div className={css.cliCodeWrap}>
                    <CodeViewer className={css.cliCode} language="bash">
                        {cliCode(data.token)}
                    </CodeViewer>

                    <Button
                        className={css.copy}
                        displayAsRound
                        dimension="s"
                        appearance="gray-transparent"
                        icon={<CopyIcon />}
                        onClick={() => copyToClipboard(cliCode(data.token))}
                    />
                </div>
            </SettingsSection>
        </div>
    );
};

export default Account;
