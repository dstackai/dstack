import React, { FC, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { product } from 'product';

import {
    Box,
    Button,
    Cards,
    Code,
    Container,
    ContentLayout,
    FormField,
    Header,
    InfoLink,
    Popover,
    PropertyFilter,
    SpaceBetween,
    Spinner,
    StatusIndicator,
} from 'components';

import { QUICK_START_URL } from 'consts';
import { useBreadcrumbs, useHelpPanel } from 'hooks';
import { copyToClipboard } from 'libs';
import { tokensToSearchParams } from 'libs/filters';
import { ROUTES } from 'routes';
import { useLazyGetGpusListQuery } from 'services/gpu';
import { useGetProjectQuery } from 'services/project';
import { useGetAllTemplatesQuery } from 'services/templates';

import { getRequestParams } from 'pages/Offers/List';
import { getOfferFilters, toRangeTokens, useFilters } from 'pages/Offers/List/hooks/useFilters';
import { useCheckAvailableProjectPermission } from 'pages/Project/hooks/useCheckAvailableProjectPermission';
import { useConfigProjectCliCommand } from 'pages/Project/hooks/useConfigProjectCliComand';

import { AGENTS_INFO, CLI_INFO, getTemplatesInfo } from './constants';
import { getApplyCommand } from './helpers';

import styles from './styles.module.scss';

const INSTALL_COMMAND = 'uv tool install dstack -U';
const SKILLS_COMMAND = 'npx skills add dstackai/dstack';
// The page layout's padding below the content.
const PAGE_BOTTOM_PADDING = 40;
// Matches the breakpoint in styles.module.scss where the columns stack.
const STACKED_COLUMNS_QUERY = '(max-width: 960px)';

export const LaunchOptions: FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const [gpus, setGpus] = useState<IGpu[]>([]);
    const [getGpus] = useLazyGetGpusListQuery();

    useBreadcrumbs([
        {
            text: t('projects.runs'),
            href: ROUTES.RUNS.LIST,
        },
        {
            text: t('runs.launch_page.title'),
            href: ROUTES.RUNS.LAUNCH,
        },
    ]);

    // The same filter as on Offers; GPU names, vendors and backends load only when their list is opened.
    const [initialFilters] = useState(() => {
        const filters = getOfferFilters(searchParams);
        return product.hasTemplates ? filters : filters?.project_name ? { project_name: filters.project_name } : {};
    });

    const loadGpus = async (projectName: string) => {
        const data = await getGpus(getRequestParams({ project_name: projectName, group_by: ['gpu'] })).unwrap();
        setGpus(data.gpus);
    };

    const {
        filteringRequestParams,
        clearFilter,
        propertyFilterRef,
        propertyFilterQuery,
        onChangePropertyFilter,
        filteringOptions,
        filteringProperties,
        filteringStatusType,
        handleLoadItems,
    } = useFilters({ gpus, withSearchParams: false, showFleetFilter: true, defaultFilters: initialFilters, loadGpus });

    // The filter owns the URL, apart from the selected template.
    useEffect(() => {
        setSearchParams(
            (params) => {
                const next = tokensToSearchParams(toRangeTokens(propertyFilterQuery.tokens));
                const template = params.get('template');

                if (template) {
                    next.set('template', template);
                }

                return next;
            },
            { replace: true },
        );
    }, [propertyFilterQuery]);

    const projectName =
        typeof filteringRequestParams.project_name === 'string' ? filteringRequestParams.project_name : undefined;

    const { currentData: templates, isFetching: isFetchingTemplates } = useGetAllTemplatesQuery(
        { projectName: projectName ?? '' },
        { skip: !product.hasTemplates || !projectName },
    );

    const renderWaysToLaunch = () => {
        if (!projectName) {
            return <Box color="text-body-secondary">{t('runs.launch_page.select_project')}</Box>;
        }

        // Templates are an Enterprise feature; without them, the CLI is the only way to launch.
        if (!product.hasTemplates) {
            return <CliColumn projectName={projectName} />;
        }

        // Waiting for the templates keeps the layout from switching once they arrive.
        if (isFetchingTemplates) {
            return <Spinner size="big" />;
        }

        return <Columns projectName={projectName} templates={templates ?? []} />;
    };

    return (
        <ContentLayout header={<Header variant="h1">{t('runs.launch_page.title')}</Header>}>
            <SpaceBetween size="l">
                <div className={styles.filter}>
                    <PropertyFilter
                        ref={propertyFilterRef}
                        query={propertyFilterQuery}
                        onChange={onChangePropertyFilter}
                        customFilterActions={
                            <Button variant="link" formAction="none" onClick={clearFilter}>
                                {t('common.clearFilter')}
                            </Button>
                        }
                        expandToViewport
                        hideOperations
                        i18nStrings={{
                            clearFiltersText: t('common.clearFilter'),
                            filteringAriaLabel: t('offer.filter_property_placeholder'),
                            filteringPlaceholder: t('offer.filter_property_placeholder'),
                        }}
                        filteringOptions={
                            product.hasTemplates
                                ? filteringOptions
                                : filteringOptions.filter(({ propertyKey }) => propertyKey === 'project_name')
                        }
                        filteringProperties={
                            product.hasTemplates
                                ? filteringProperties
                                : filteringProperties.filter(({ key }) => key === 'project_name')
                        }
                        filteringStatusType={filteringStatusType}
                        onLoadItems={handleLoadItems}
                    />
                </div>

                {renderWaysToLaunch()}
            </SpaceBetween>
        </ContentLayout>
    );
};

// Reaches the window's bottom; extra height goes to the CLI card and the template cards.
const Columns: FC<{ projectName: string; templates: ITemplate[] }> = ({ projectName, templates }) => {
    const columnsRef = useRef<HTMLDivElement>(null);
    const minHeight = useHeightToWindowBottom(columnsRef);

    return (
        <div ref={columnsRef} className={styles.columns} style={{ minHeight }}>
            <CliColumn projectName={projectName} />

            {/* Fills the row, so the template cards scroll inside it. */}
            <div className={styles.templatesCell}>
                <div className={styles.templatesFill}>
                    <TemplatePanel projectName={projectName} templates={templates} />
                </div>
            </div>
        </div>
    );
};

const CliColumn: FC<{ projectName: string }> = ({ projectName }) => (
    <div className={styles.cliColumn}>
        <div className={styles.cliFill}>
            <CliPanel projectName={projectName} />
        </div>
        <AgentsPanel />
    </div>
);

const CliPanel: FC<{ projectName: string }> = ({ projectName }) => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const [openHelpPanel] = useHelpPanel();
    const [configCliCommand] = useConfigProjectCliCommand({ projectName });

    return (
        <Container
            fitHeight
            header={
                <Header
                    variant="h2"
                    info={<InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />}
                    actions={
                        <Button href={QUICK_START_URL} target="_blank" iconName="external" iconAlign="right">
                            {t('runs.launch_page.docs')}
                        </Button>
                    }
                >
                    {t('runs.launch_page.cli_title')}
                </Header>
            }
        >
            <SpaceBetween size="m">
                <FormField label={t('runs.launch_page.cli_install')}>
                    <CopyableCode command={INSTALL_COMMAND} />
                </FormField>

                <FormField label={t('runs.launch_page.cli_add_project')}>
                    <CopyableCode command={configCliCommand} />
                </FormField>

                <FormField
                    label={t('runs.launch_page.cli_define')}
                    info={<InfoLink onFollow={() => openHelpPanel(CLI_INFO)} />}
                >
                    <Box>
                        <Trans i18nKey="runs.launch_page.cli_define_text" components={{ code: <Box variant="code" /> }} />
                    </Box>
                </FormField>

                <FormField label={t('runs.launch_page.cli_apply')}>
                    <CopyableCode command={getApplyCommand(searchParams)} />
                </FormField>
            </SpaceBetween>
        </Container>
    );
};

const AgentsPanel: FC = () => {
    const { t } = useTranslation();
    const [openHelpPanel] = useHelpPanel();

    return (
        <Container
            header={
                <Header
                    variant="h2"
                    description={
                        <Trans i18nKey="runs.launch_page.agents_description" components={{ code: <Box variant="code" /> }} />
                    }
                    info={<InfoLink onFollow={() => openHelpPanel(AGENTS_INFO)} />}
                >
                    {t('runs.launch_page.agents_title')}
                </Header>
            }
        >
            <CopyableCode command={SKILLS_COMMAND} />
        </Container>
    );
};

const TemplatePanel: FC<{ projectName: string; templates: ITemplate[] }> = ({ projectName, templates }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [openHelpPanel] = useHelpPanel();
    const { isProjectAdmin } = useCheckAvailableProjectPermission();
    const { data: project } = useGetProjectQuery({ name: projectName }, { skip: templates.length > 0 });
    const isAdmin = !!project && isProjectAdmin(project);

    // The selected template lives in the URL, like the project, so a refresh or a shared link keeps it.
    const [searchParams, setSearchParams] = useSearchParams();
    const selectedTemplate = templates.find(({ name }) => name === searchParams.get('template'));

    // Keeps the other params, such as a GPU picked on the Offers page.
    const selectTemplate = (template?: ITemplate) => {
        setSearchParams(
            (params) => {
                if (template) {
                    params.set('template', template.name);
                } else {
                    params.delete('template');
                }
                return params;
            },
            { replace: true },
        );
    };

    // The wizard starts at Resources, with the project, the template and any GPU picked on the Offers page.
    const openWizard = () => {
        const params = new URLSearchParams(searchParams);
        params.set('project_name', projectName);
        params.set('step', 'resources');
        navigate(`${ROUTES.RUNS.CREATE_DEV_ENV}?${params}`);
    };

    const renderNoTemplates = () => (
        <SpaceBetween size="m">
            <SpaceBetween size="xxs">
                <Box variant="strong">{t('runs.no_templates_alert.title')}</Box>
                <Box color="text-body-secondary">{t('runs.launch_page.no_templates_text')}</Box>
            </SpaceBetween>

            {isAdmin && (
                <Button onClick={() => navigate(`${ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(projectName)}#danger-zone`)}>
                    {t('runs.no_templates_alert.action')}
                </Button>
            )}
        </SpaceBetween>
    );

    return (
        <Container
            fitHeight
            header={
                <Header
                    variant="h2"
                    info={<InfoLink onFollow={() => openHelpPanel(getTemplatesInfo(projectName))} />}
                    actions={
                        templates.length > 0 && (
                            // Hidden, not removed, until a template is selected, so the header keeps its height.
                            <span className={selectedTemplate ? undefined : styles.hidden} aria-hidden={!selectedTemplate}>
                                <Button variant="primary" disabled={!selectedTemplate} onClick={openWizard}>
                                    {t('common.next')}
                                </Button>
                            </span>
                        )
                    }
                >
                    {t('runs.launch_page.template_title')}
                </Header>
            }
        >
            {templates.length ? (
                <Cards
                    items={templates}
                    trackBy="name"
                    selectionType="single"
                    entireCardClickable
                    selectedItems={selectedTemplate ? [selectedTemplate] : []}
                    onSelectionChange={({ detail }) => selectTemplate(detail.selectedItems[0])}
                    cardsPerRow={[{ cards: 1 }, { minWidth: 400, cards: 2 }, { minWidth: 700, cards: 3 }]}
                    cardDefinition={{
                        header: (template) => template.title,
                        sections: [{ id: 'description', content: (template) => template.description ?? '' }],
                    }}
                />
            ) : (
                renderNoTemplates()
            )}
        </Container>
    );
};

// From the element's top to the window's bottom; none when the columns stack.
const useHeightToWindowBottom = (ref: React.RefObject<HTMLElement>): number | undefined => {
    const [height, setHeight] = useState<number>();

    useLayoutEffect(() => {
        const update = () => {
            if (!ref.current || window.matchMedia(STACKED_COLUMNS_QUERY).matches) {
                setHeight(undefined);
                return;
            }

            const top = ref.current.getBoundingClientRect().top + window.scrollY;
            setHeight(window.innerHeight - top - PAGE_BOTTOM_PADDING);
        };

        update();
        window.addEventListener('resize', update);
        return () => window.removeEventListener('resize', update);
    }, []);

    return height;
};

const CopyableCode: FC<{ command: string }> = ({ command }) => {
    const { t } = useTranslation();

    return (
        <div className={styles.codeWrapper}>
            <Code className={styles.code}>{command}</Code>

            <div className={styles.copy}>
                <Popover
                    dismissButton={false}
                    position="top"
                    size="small"
                    triggerType="custom"
                    content={<StatusIndicator type="success">{t('common.copied')}</StatusIndicator>}
                >
                    <Button formAction="none" iconName="copy" variant="normal" onClick={() => copyToClipboard(command)} />
                </Popover>
            </div>
        </div>
    );
};
