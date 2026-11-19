import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useMatch, useParams } from 'react-router-dom';

import {
    Alert,
    Box,
    Button,
    Code,
    Container,
    ContentLayout,
    DetailsHeader,
    Loader,
    Modal,
    SpaceBetween,
    Tabs,
    TokenVisibilityButton,
} from 'components';

import { useAppSelector, useBreadcrumbs } from 'hooks';
import { copyToClipboard, getServerError, riseRouterException, TOKEN_MASK } from 'libs';
import { ROUTES } from 'routes';

import { selectAuthToken } from 'App/slice';

import { getCurlModelCode, getModelUrl, getPythonModelCode } from './helpers';
import { useModel } from './hooks';

import styles from './styles.module.scss';

enum ModelTab {
    Details = 'details',
    Usage = 'usage',
}

enum CodeTab {
    Python = 'python',
    Curl = 'curl',
}

export const ModelDetailsPage: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const [viewCodeVisible, setViewCodeVisible] = useState<boolean>(false);
    const [codeTab, setCodeTab] = useState<CodeTab>(CodeTab.Python);
    const [isTokenVisible, setIsTokenVisible] = useState<boolean>(false);
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramModelName = params.modelName ?? '';
    const matchUsage = useMatch(ROUTES.MODELS.DETAILS.USAGE.TEMPLATE);

    const { model, isLoading, error, isNotFound, hasUsage } = useModel(paramProjectName, paramModelName);

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
            text: paramModelName,
            href: ROUTES.MODELS.DETAILS.FORMAT(paramProjectName, paramModelName),
        },
    ]);

    useEffect(() => {
        if (isNotFound) {
            riseRouterException();
        }
    }, [isNotFound]);

    const closeViewCode = () => {
        setViewCodeVisible(false);
        setIsTokenVisible(false);
    };

    const displayedToken = isTokenVisible ? token : TOKEN_MASK;

    const pythonCode = getPythonModelCode({ model, token: displayedToken });

    const curlCode = getCurlModelCode({ model, token: displayedToken });

    const onCopyCode = () => {
        switch (codeTab) {
            case CodeTab.Python:
                return copyToClipboard(getPythonModelCode({ model, token }));
            case CodeTab.Curl:
                return copyToClipboard(getCurlModelCode({ model, token }));
        }
    };

    const tabs = [
        {
            label: t('models.details.title'),
            id: ModelTab.Details,
            href: ROUTES.MODELS.DETAILS.FORMAT(paramProjectName, paramModelName),
        },
        hasUsage && {
            label: t('models.usage.title'),
            id: ModelTab.Usage,
            href: ROUTES.MODELS.DETAILS.USAGE.FORMAT(paramProjectName, paramModelName),
        },
    ].filter(Boolean) as {
        label: string;
        id: ModelTab;
        href: string;
    }[];

    // A user who doesn't get the Usage tab doesn't get its page either
    if (model && matchUsage && !hasUsage) {
        return <Navigate to={ROUTES.MODELS.DETAILS.FORMAT(paramProjectName, paramModelName)} replace />;
    }

    return (
        <div className={styles.page}>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramModelName}
                        actionButtons={
                            <Button disabled={!getModelUrl(model)} onClick={() => setViewCodeVisible(true)}>
                                {t('models.code')}
                            </Button>
                        }
                    />
                }
            >
                {isLoading && (
                    <Container>
                        <Loader />
                    </Container>
                )}

                {error && <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>}

                {model && (
                    <>
                        <Tabs withNavigation tabs={tabs} activeTabId={matchUsage ? ModelTab.Usage : ModelTab.Details} />

                        {/* Remount tabs on model change so the chat and the filters of one model don't show for another */}
                        <Outlet key={`${paramProjectName}/${paramModelName}`} context={model} />
                    </>
                )}
            </ContentLayout>

            <Modal
                visible={viewCodeVisible}
                header={t('models.details.view_code')}
                size="large"
                footer={
                    <Box float="right">
                        <Button variant="normal" onClick={closeViewCode}>
                            {t('common.close')}
                        </Button>
                    </Box>
                }
                onDismiss={closeViewCode}
            >
                <SpaceBetween size="m" direction="vertical">
                    <Box>{t('models.details.view_code_description')}</Box>

                    <div className={styles.viewCodeControls}>
                        <div className={styles.copyButton}>
                            <SpaceBetween direction="horizontal" size="xs">
                                <TokenVisibilityButton visible={isTokenVisible} onChange={setIsTokenVisible} />
                                <Button iconName="copy" onClick={onCopyCode}></Button>
                            </SpaceBetween>
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
        </div>
    );
};
