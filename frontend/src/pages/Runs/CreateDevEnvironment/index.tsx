import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import cn from 'classnames';
import { Box, Link, WizardProps } from '@cloudscape-design/components';
import { CardsProps } from '@cloudscape-design/components/cards';

import { Container, FormCodeEditor, FormField, FormSelect, SpaceBetween, Wizard } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { useCheckingForFleetsInProjects } from 'hooks/useCheckingForFleetsInProjectsOfMember';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useApplyRunMutation } from 'services/run';
import { useGetAllTemplatesQuery } from 'services/templates';

import { OfferList } from 'pages/Offers/List';
import { NoFleetProjectAlert } from 'pages/Project/components/NoFleetProjectAlert';

import { ParamsWizardStep } from './components/ParamsWizardStep';
import { useGenerateYaml } from './hooks/useGenerateYaml';
import { useGetRunSpecFromYaml } from './hooks/useGetRunSpecFromYaml';
import { useYupValidationResolver } from './hooks/useValidationResolver';
import { FORM_FIELD_NAMES } from './constants';

import { IRunEnvironmentFormKeys, IRunEnvironmentFormValues } from './types';

import styles from './styles.module.scss';

const templateStepFieldNames: IRunEnvironmentFormKeys[] = [FORM_FIELD_NAMES.project, FORM_FIELD_NAMES.template];
const offerStepFieldNames: IRunEnvironmentFormKeys[] = [FORM_FIELD_NAMES.offer];
const configStepFieldNames: IRunEnvironmentFormKeys[] = [FORM_FIELD_NAMES.config_yaml];

const paramsStepFieldNames = Object.keys(FORM_FIELD_NAMES).filter(
    (fieldName) =>
        ![...templateStepFieldNames, ...offerStepFieldNames, ...configStepFieldNames].includes(
            fieldName as IRunEnvironmentFormKeys,
        ),
) as IRunEnvironmentFormKeys[];

export const CreateDevEnvironment: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [selectedOffers, setSelectedOffers] = useState<IGpu[]>([]);
    const [selectedTemplate, setSelectedTemplate] = useState<ITemplate | undefined>();
    const { projectOptions, isLoadingProjectOptions } = useProjectFilter({ localStorePrefix: 'run-env-list-projects' });

    const [applyRun, { isLoading: isApplying }] = useApplyRunMutation();

    const loading = isApplying;

    useBreadcrumbs([
        {
            text: t('projects.runs'),
            href: ROUTES.RUNS.LIST,
        },
        {
            text: t('runs.dev_env.wizard.title'),
            href: ROUTES.RUNS.CREATE_DEV_ENV,
        },
    ]);

    const resolver = useYupValidationResolver(selectedTemplate);

    const formMethods = useForm<IRunEnvironmentFormValues>({
        resolver,
        defaultValues: {
            project: searchParams.get('project_name') ?? undefined,
        },
    });

    const { handleSubmit, control, trigger, setValue, watch, formState, getValues } = formMethods;
    const formValues = watch();

    const projectHavingFleetMap = useCheckingForFleetsInProjects({
        projectNames: formValues.project ? [formValues.project] : [],
    });

    const projectDontHasFleets = !!formValues.project && !projectHavingFleetMap[formValues.project];
    const [getRunSpecFromYaml] = useGetRunSpecFromYaml({ projectName: formValues.project ?? '' });

    const { data: templatesData, isLoading: isLoadingTemplates } = useGetAllTemplatesQuery(
        { projectName: formValues.project ?? '' },
        { skip: !formValues.project },
    );

    const templateOptions = useMemo(() => {
        if (!templatesData) {
            return [];
        }

        return templatesData.map((template) => ({
            label: template.title,
            value: template.id,
        }));
    }, [templatesData]);

    useEffect(() => {
        setSelectedTemplate(templatesData?.find((t) => t.id === formValues.template));
    }, [templatesData, formValues.template]);

    const validateProjectAndTemplate = async () => await trigger(templateStepFieldNames);
    const validateOffer = async () => await trigger(offerStepFieldNames);
    const validateConfigParams = async () => await trigger(paramsStepFieldNames);
    const validateConfig = async () => await trigger(configStepFieldNames);

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateProjectAndTemplate, validateOffer, validateConfigParams, validateConfig];

        if (reason === 'next') {
            if (projectDontHasFleets) {
                window.scrollTo(0, 0);
            }

            stepValidators[activeStepIndex]?.().then((isValid) => {
                if (isValid) {
                    setActiveStepIndex(requestedStepIndex);
                } else if (activeStepIndex == 0) {
                    window.scrollTo(0, 0);
                }
            });
        } else {
            setActiveStepIndex(requestedStepIndex);
        }
    };

    const onNavigateHandler: WizardProps['onNavigate'] = ({ detail: { requestedStepIndex, reason } }) => {
        onNavigate({ requestedStepIndex, reason });
    };

    const onChangeOffer: CardsProps<IGpu>['onSelectionChange'] = ({ detail }) => {
        const newSelectedOffers = detail?.selectedItems ?? [];
        setSelectedOffers(newSelectedOffers);
        setValue(FORM_FIELD_NAMES.offer, newSelectedOffers?.[0] ?? null);
    };

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        if (!isValid) {
            return;
        }

        const { config_yaml } = getValues();

        let runSpec;

        try {
            runSpec = await getRunSpecFromYaml(config_yaml);
        } catch (e) {
            console.log('parse transaction error:', e);
            return;
        }

        const requestParams: TRunApplyRequestParams = {
            project_name: formValues.project,
            plan: {
                run_spec: runSpec,
            },
            force: false,
        };

        applyRun(requestParams)
            .unwrap()
            .then((data) => {
                pushNotification({
                    type: 'success',
                    content: t('runs.dev_env.wizard.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(data.project_name, data.id));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const onSubmit = () => {
        if (activeStepIndex < 3) {
            onNavigate({ requestedStepIndex: activeStepIndex + 1, reason: 'next' });
        } else {
            onSubmitWizard().catch(console.log);
        }
    };

    const yaml = useGenerateYaml({ formValues, template: selectedTemplate?.template });

    useEffect(() => {
        setValue(FORM_FIELD_NAMES.config_yaml, yaml);
    }, [yaml]);

    const onCancelHandler = () => {
        navigate(ROUTES.RUNS.LIST);
    };

    return (
        <form className={cn({ [styles.wizardForm]: activeStepIndex === 0 })} onSubmit={handleSubmit(onSubmit)}>
            <NoFleetProjectAlert
                className={styles.noFleetAlert}
                projectName={formValues.project ?? ''}
                show={projectDontHasFleets}
            />

            <Wizard
                activeStepIndex={activeStepIndex}
                onNavigate={onNavigateHandler}
                onSubmit={onSubmitWizard}
                i18nStrings={{
                    stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
                    navigationAriaLabel: 'Steps',
                    cancelButton: t('common.cancel'),
                    previousButton: t('common.previous'),
                    nextButton: t('common.next'),
                    optional: 'optional',
                }}
                onCancel={onCancelHandler}
                submitButtonText={t('runs.dev_env.wizard.submit')}
                steps={[
                    {
                        title: 'Template',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormSelect
                                        label={t('runs.dev_env.wizard.project')}
                                        description={t('runs.dev_env.wizard.project_description')}
                                        control={control}
                                        name={FORM_FIELD_NAMES.project}
                                        options={projectOptions}
                                        disabled={loading}
                                        empty={t('runs.dev_env.wizard.project_empty')}
                                        loadingText={t('runs.dev_env.wizard.project_loading')}
                                        statusType={isLoadingProjectOptions ? 'loading' : undefined}
                                        onChange={() => setValue(FORM_FIELD_NAMES.template, '')}
                                    />

                                    <FormSelect
                                        label={t('runs.dev_env.wizard.template')}
                                        description={t('runs.dev_env.wizard.template_description')}
                                        placeholder={
                                            !formValues.project ? t('runs.dev_env.wizard.template_placeholder') : undefined
                                        }
                                        control={control}
                                        name={FORM_FIELD_NAMES.template}
                                        options={templateOptions}
                                        disabled={loading}
                                        empty={t('runs.dev_env.wizard.template_empty')}
                                        loadingText={t('runs.dev_env.wizard.template_loading')}
                                        statusType={isLoadingTemplates ? 'loading' : undefined}
                                    />
                                </SpaceBetween>
                            </Container>
                        ),
                    },

                    {
                        title: 'Resources',
                        content: (
                            <>
                                <FormField
                                    label={t('runs.dev_env.wizard.offer')}
                                    description={t('runs.dev_env.wizard.offer_description')}
                                    errorText={formState.errors.offer?.message}
                                />

                                {formState.errors.offer?.message && <br />}

                                <OfferList
                                    selectionType="single"
                                    withSearchParams={false}
                                    selectedItems={selectedOffers}
                                    onSelectionChange={onChangeOffer}
                                    permanentFilters={{ project_name: formValues.project ?? '' }}
                                />
                            </>
                        ),
                    },

                    {
                        title: 'Settings',
                        content: <ParamsWizardStep formMethods={formMethods} loading={loading} template={selectedTemplate} />,
                    },

                    {
                        title: 'Configuration',
                        content: (
                            <Container>
                                <FormCodeEditor
                                    control={control}
                                    description={
                                        <Box>
                                            Review the configuration file and adjust it if needed. See{' '}
                                            <Link
                                                href="https://docs.dstack.ai/docs/concepts/dev-environments"
                                                target="_blank"
                                                external
                                            >
                                                examples
                                            </Link>
                                            .
                                        </Box>
                                    }
                                    name={FORM_FIELD_NAMES.config_yaml}
                                    language="yaml"
                                    loading={loading}
                                    editorContentHeight={600}
                                />
                            </Container>
                        ),
                    },
                ]}
            />
        </form>
    );
};
