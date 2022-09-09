import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ReactComponent as GithubCircleIcon } from 'assets/icons/github-circle.svg';
import Table, { Cell, Row } from 'components/Table';
import ConfirmModal from 'components/ConfirmModal';
import Button from 'components/Button';
import TableContentSkeleton from 'components/TableContentSkeleton';
import SettingsSection from 'pages/Settings/components/Section';
import { useGetUserInfoQuery, useUnlinkGithubAccountMutation } from 'services/user';
import { arrayToRecordByKeyName, createUrlWithBase, goToUrl } from 'libs';
import { ITableColumn } from 'components/Table/types';

import css from './index.module.css';

const columns: ITableColumn[] = [
    {
        name: 'git',
        title: 'Git',
        type: 'empty',
        width: 48,
    },
    {
        name: 'username',
        title: 'Username',
        type: 'text',
        width: 160,
    },
];

const mappedColumns = arrayToRecordByKeyName(columns, 'name');

const githubEnabled = process.env.GITHUB_ENABLED;

const SettingsGit: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
    const { data, isLoading } = useGetUserInfoQuery();
    const [unlinkGithub] = useUnlinkGithubAccountMutation();

    const goToConfigurePermission = () => {
        goToUrl(createUrlWithBase(process.env.API_URL, '/users/github/config'));
    };

    const deleteGithub = () => {
        unlinkGithub();
        setShowDeleteConfirm(false);
    };

    const linkGitHubAccount = () => {
        goToUrl(createUrlWithBase(process.env.API_URL, '/users/github/link'));
    };

    if (!data || isLoading) return <TableContentSkeleton />;

    return (
        <div className={css.git}>
            <SettingsSection>
                <SettingsSection.Title>{t('credentials')}</SettingsSection.Title>
                <SettingsSection.Text>{t('to_run_workflows_dstack_requires_git_access')}</SettingsSection.Text>

                <Table className={css.table} columns={columns} withContextMenu>
                    {githubEnabled && data.github_user_name && (
                        <Row columns={columns}>
                            <Cell
                                cell={{
                                    ...mappedColumns['git'],
                                    dataType: 'empty',
                                }}
                            >
                                <GithubCircleIcon width={24} height={24} />
                            </Cell>

                            <Cell
                                cell={{
                                    ...mappedColumns['username'],
                                    dataType: 'text',
                                    data: data.github_user_name,
                                }}
                            />

                            <Row.ContextMenu autoHidden={false}>
                                <Row.EditButton onClick={goToConfigurePermission} />
                                <Row.DeleteButton onClick={() => setShowDeleteConfirm(true)} />
                            </Row.ContextMenu>
                        </Row>
                    )}
                </Table>

                {githubEnabled && (
                    <Button
                        appearance="blue-fill"
                        className={css.addButton}
                        onClick={linkGitHubAccount}
                        disabled={!!data.github_user_name}
                    >
                        {t('add_github_account')}
                    </Button>
                )}
            </SettingsSection>

            <ConfirmModal
                show={showDeleteConfirm}
                close={() => setShowDeleteConfirm(false)}
                ok={deleteGithub}
                title={t('delete')}
                confirmButtonProps={{ children: t('yes_delete'), appearance: 'red-stroke' }}
            >
                {t('confirm_messages.delete_git')}
            </ConfirmModal>
        </div>
    );
};

export default SettingsGit;
