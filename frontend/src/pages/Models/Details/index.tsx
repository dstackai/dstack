import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { product } from 'product';

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
    SelectCSD,
    SpaceBetween,
    Tabs,
    TokenVisibilityButton,
} from 'components';

import { useAppSelector, useBreadcrumbs } from 'hooks';
import { copyToClipboard, getServerError, riseRouterException, TOKEN_MASK } from 'libs';
import { ROUTES } from 'routes';

import { selectAuthToken } from 'App/slice';

import { ModelExports } from './Exports';
import { getCurlModelCode, getModelUrl, getPythonModelCode } from './helpers';
import { useModel } from './hooks';
import { ModelDetails } from './ModelDetails';
import { ModelUsage } from './Usage';

import styles from './styles.module.scss';

enum ModelTab {
    Details = 'details',
    Exports = 'exports',
    Metering = 'metering',
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
    const [codeProjectName, setCodeProjectName] = useState<IProject['project_name']>();
    const params = useParams();
    const paramProjectName = params.projectName ?? '';
    const paramModelName = params['*'] ?? '';
    const [searchParams] = useSearchParams();
    const isMeteringTab = searchParams.get('tab') === ROUTES.MODELS.DETAILS.METERING.TAB;
    // Exports exist only where the server enables them
    const isExportsTab = product.hasExports && searchParams.get('tab') === ROUTES.MODELS.DETAILS.EXPORTS.TAB;

    const { model, isLoading, error, isNotFound, hasUsage, projects, projectsImports } = useModel(
        paramProjectName,
        paramModelName,
    );

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

    // The user's projects through which the model can be accessed now. The code is for the chosen one, else for the first
    const codeProjectOptions = (model?.endpoints ?? [])
        .filter(({ base_url }) => base_url)
        .map(({ project_name }) => ({ label: project_name, value: project_name }));

    const codeProjectOption = codeProjectOptions.find(({ value }) => value === codeProjectName) ?? codeProjectOptions[0];
    const codeParams = { model, projectName: codeProjectOption?.value };

    const pythonCode = getPythonModelCode({ ...codeParams, token: displayedToken });

    const curlCode = getCurlModelCode({ ...codeParams, token: displayedToken });

    const onCopyCode = () => {
        switch (codeTab) {
            case CodeTab.Python:
                return copyToClipboard(getPythonModelCode({ ...codeParams, token }));
            case CodeTab.Curl:
                return copyToClipboard(getCurlModelCode({ ...codeParams, token }));
        }
    };

    const tabs = [
        {
            label: t('models.details.title'),
            id: ModelTab.Details,
            href: ROUTES.MODELS.DETAILS.FORMAT(paramProjectName, paramModelName),
        },
        product.hasExports && {
            label: t('models.exports.title'),
            id: ModelTab.Exports,
            href: ROUTES.MODELS.DETAILS.EXPORTS.FORMAT(paramProjectName, paramModelName),
        },
        hasUsage && {
            label: t('models.metering'),
            id: ModelTab.Metering,
            href: ROUTES.MODELS.DETAILS.METERING.FORMAT(paramProjectName, paramModelName),
        },
    ].filter(Boolean) as {
        label: string;
        id: ModelTab;
        href: string;
    }[];

    const activeTabId = isMeteringTab ? ModelTab.Metering : isExportsTab ? ModelTab.Exports : ModelTab.Details;
    const modelKey = `${paramProjectName}/${paramModelName}`;

    // A user who doesn't get the Metering tab doesn't get its page either
    if (model && isMeteringTab && !hasUsage) {
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
                                {t('models.endpoint')}
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
                        <Tabs withNavigation tabs={tabs} activeTabId={activeTabId} />

                        {/* Remount tabs on model change so the chat and the filters of one model don't show for another */}
                        {activeTabId === ModelTab.Details && <ModelDetails key={modelKey} model={model} />}
                        {activeTabId === ModelTab.Exports && (
                            <ModelExports key={modelKey} model={model} projects={projects} projectsImports={projectsImports} />
                        )}
                        {activeTabId === ModelTab.Metering && <ModelUsage key={modelKey} model={model} />}
                    </>
                )}
            </ContentLayout>

            <Modal
                visible={viewCodeVisible}
                header={t('models.endpoint')}
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
                            actions={
                                codeProjectOptions.length > 1 && (
                                    <div className={styles.codeProject}>
                                        <SelectCSD
                                            inlineLabelText={t('models.project')}
                                            selectedOption={codeProjectOption}
                                            options={codeProjectOptions}
                                            onChange={({ detail }) => setCodeProjectName(detail.selectedOption.value)}
                                        />
                                    </div>
                                )
                            }
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
