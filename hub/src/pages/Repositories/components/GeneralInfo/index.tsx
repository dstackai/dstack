import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { Box, ColumnLayout, Container, Header } from 'components';

import { DATE_TIME_FORMAT } from 'consts';

import { RepoTypeEnum } from '../../types';

export type Props = IRepo;

export const RepositoryGeneralInfo: React.FC<Props> = (repo) => {
    const { t } = useTranslation();

    return (
        <Container header={<Header variant="h2">{t('common.general')}</Header>}>
            <ColumnLayout columns={4} variant="text-grid">
                <div>
                    <Box variant="awsui-key-label">{t('projects.repo.card.last_run')}</Box>
                    <div>{format(new Date(repo.last_run_at), DATE_TIME_FORMAT)}</div>
                </div>

                {repo.repo_info.repo_type === RepoTypeEnum.LOCAL && (
                    <div>
                        <Box variant="awsui-key-label">{t('projects.repo.card.directory')}</Box>
                        <div>{repo.repo_info.repo_dir}</div>
                    </div>
                )}
            </ColumnLayout>
        </Container>
    );
};
