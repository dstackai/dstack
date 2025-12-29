import React, { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import cn from 'classnames';
import * as yup from 'yup';
import { Box, Link, WizardProps } from '@cloudscape-design/components';
import { CardsProps } from '@cloudscape-design/components/cards';

import { TabsProps, ToggleProps } from 'components';
import { Container, FormCodeEditor, FormField, FormInput, FormSelect, SpaceBetween, Tabs, Toggle, Wizard } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { useCheckingForFleetsInProjects } from 'hooks/useCheckingForFleetsInProjectsOfMember';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useApplyRunMutation } from 'services/run';

import { OfferList } from 'pages/Offers/List';
import { NoFleetProjectAlert } from 'pages/Project/components/NoFleetProjectAlert';

import { useGenerateYaml } from './hooks/useGenerateYaml';
import { useGetRunSpecFromYaml } from './hooks/useGetRunSpecFromYaml';
import { FORM_FIELD_NAMES } from './constants';

import { IRunEnvironmentFormKeys, IRunEnvironmentFormValues } from './types';

import styles from './styles.module.scss';

const requiredFieldError = 'This is a required field';
const namesFieldError = 'Only latin characters, dashes, and digits';
const urlFormatError = 'Only URLs';
const workingDirFormatError = 'Must be an absolute path';

const ideOptions = [
    {
        label: 'Cursor',
        value: 'cursor',
    },
    {
        label: 'VS Code',
        value: 'vscode',
    },
];

enum DockerPythonTabs {
    DOCKER = 'docker',
    PYTHON = 'python',
}

const envValidationSchema = yup.object({
    offer: yup.object().required(requiredFieldError),
    name: yup.string().matches(/^[a-z][a-z0-9-]{1,40}$/, namesFieldError),
    ide: yup.string().required(requiredFieldError),
    config_yaml: yup.string().required(requiredFieldError),
    working_dir: yup.string().matches(/^\//, workingDirFormatError),

    image: yup.string().when('docker', {
        is: true,
        then: yup.string().required(requiredFieldError),
    }),

    repo_url: yup.string().when('repo_enabled', {
        is: true,
        then: yup
            .string()
            .matches(/^(https?):\/\/([^\s\/?#]+)((?:\/[^\s?#]*)*)(?::\/(.*))?$/i, urlFormatError)
            .required(requiredFieldError),
    }),
});

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error
const useYupValidationResolver = (validationSchema) =>
    useCallback(
        async (data: IRunEnvironmentFormValues) => {
            try {
                const values = await validationSchema.validate(data, {
                    abortEarly: false,
                });

                return {
                    values,
                    errors: {},
                };
            } catch (errors) {
                return {
                    values: {},
                    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                    // @ts-expect-error
                    errors: errors.inner.reduce(
                        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                        // @ts-expect-error
                        (allErrors, currentError) => ({
                            ...allErrors,
                            [currentError.path]: {
                                type: currentError.type ?? 'validation',
                                message: currentError.message,
                            },
                        }),
                        {},
                    ),
                };
            }
        },
        [validationSchema],
    );

export const CreateDevEnvironment: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [selectedOffers, setSelectedOffers] = useState<IGpu[]>([]);
    const [selectedProject, setSelectedProject] = useState<IProject['project_name'] | null>(
        () => searchParams.get('project_name') ?? null,
    );

    const [getRunSpecFromYaml] = useGetRunSpecFromYaml({ projectName: selectedProject ?? '' });

    const projectHavingFleetMap = useCheckingForFleetsInProjects({ projectNames: selectedProject ? [selectedProject] : [] });
    const projectDontHasFleets = !!selectedProject && !projectHavingFleetMap[selectedProject];

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

    const resolver = useYupValidationResolver(envValidationSchema);
    const formMethods = useForm<IRunEnvironmentFormValues>({
        resolver,
        defaultValues: {
            ide: 'cursor',
            docker: false,
            repo_enabled: false,
        },
    });
    const { handleSubmit, control, trigger, setValue, watch, formState, getValues } = formMethods;
    const formValues = watch();

    const onCancelHandler = () => {
        navigate(ROUTES.RUNS.LIST);
    };

    const validateOffer = async () => {
        return await trigger(['offer']);
    };

    const validateSecondStep = async () => {
        const secondStepFields = Object.keys(FORM_FIELD_NAMES).filter(
            (fieldName) => !['offer', 'config_yaml'].includes(fieldName),
        ) as IRunEnvironmentFormKeys[];

        return await trigger(secondStepFields);
    };

    const validateConfig = async () => {
        return await trigger(['config_yaml']);
    };

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateOffer, validateSecondStep, validateConfig];

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

    const toggleRepo: ToggleProps['onChange'] = ({ detail }) => {
        setValue('repo_enabled', detail.checked);

        if (!detail.checked) {
            setValue('repo_url', '');
            setValue('repo_path', '');
        }
    };

    const onChangeTab: TabsProps['onChange'] = ({ detail }) => {
        if (detail.activeTabId === DockerPythonTabs.DOCKER) {
            setValue('python', '');
        }

        if (detail.activeTabId === DockerPythonTabs.PYTHON) {
            setValue('image', '');
        }

        setValue('docker', detail.activeTabId === DockerPythonTabs.DOCKER);
    };

    const onChangeOffer: CardsProps<IGpu>['onSelectionChange'] = ({ detail }) => {
        const newSelectedOffers = detail?.selectedItems ?? [];
        setSelectedOffers(newSelectedOffers);
        setValue('offer', newSelectedOffers?.[0] ?? null);
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
            project_name: selectedProject ?? '',
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

    const yaml = useGenerateYaml({ formValues });

    useEffect(() => {
        setValue('config_yaml', yaml);
    }, [yaml]);

    return (
        <form className={cn({ [styles.wizardForm]: activeStepIndex === 0 })} onSubmit={handleSubmit(onSubmit)}>
            <NoFleetProjectAlert
                className={styles.noFleetAlert}
                projectName={selectedProject ?? ''}
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
                                    onChangeProjectName={(projectName) => setSelectedProject(projectName)}
                                    selectionType="single"
                                    withSearchParams={false}
                                    selectedItems={selectedOffers}
                                    onSelectionChange={onChangeOffer}
                                />
                            </>
                        ),
                    },

                    {
                        title: 'Settings',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormInput
                                        label={t('runs.dev_env.wizard.name')}
                                        description={t('runs.dev_env.wizard.name_description')}
                                        constraintText={t('runs.dev_env.wizard.name_constraint')}
                                        placeholder={t('runs.dev_env.wizard.name_placeholder')}
                                        control={control}
                                        name="name"
                                        disabled={loading}
                                    />

                                    <FormSelect
                                        label={t('runs.dev_env.wizard.ide')}
                                        description={t('runs.dev_env.wizard.ide_description')}
                                        control={control}
                                        name="ide"
                                        options={ideOptions}
                                        disabled={loading}
                                    />

                                    <Tabs
                                        onChange={onChangeTab}
                                        tabs={[
                                            {
                                                label: t('runs.dev_env.wizard.python'),
                                                id: DockerPythonTabs.PYTHON,
                                                content: (
                                                    <div>
                                                        <FormInput
                                                            label={t('runs.dev_env.wizard.python')}
                                                            description={t('runs.dev_env.wizard.python_description')}
                                                            placeholder={t('runs.dev_env.wizard.python_placeholder')}
                                                            control={control}
                                                            name="python"
                                                            disabled={loading}
                                                        />
                                                    </div>
                                                ),
                                            },
                                            {
                                                label: t('runs.dev_env.wizard.docker'),
                                                id: DockerPythonTabs.DOCKER,
                                                content: (
                                                    <div>
                                                        <FormInput
                                                            label={t('runs.dev_env.wizard.docker_image')}
                                                            description={t('runs.dev_env.wizard.docker_image_description')}
                                                            constraintText={t('runs.dev_env.wizard.docker_image_constraint')}
                                                            placeholder={t('runs.dev_env.wizard.docker_image_placeholder')}
                                                            control={control}
                                                            name="image"
                                                            disabled={loading}
                                                        />
                                                    </div>
                                                ),
                                            },
                                        ]}
                                    />

                                    <FormInput
                                        label={t('runs.dev_env.wizard.working_dir')}
                                        description={t('runs.dev_env.wizard.working_dir_description')}
                                        constraintText={t('runs.dev_env.wizard.working_dir_constraint')}
                                        placeholder={t('runs.dev_env.wizard.working_dir_placeholder')}
                                        control={control}
                                        name="working_dir"
                                        disabled={loading}
                                    />

                                    <Toggle checked={!!formValues.repo_enabled} onChange={toggleRepo}>
                                        {t('runs.dev_env.wizard.repo')}
                                    </Toggle>

                                    {formValues.repo_enabled && (
                                        <>
                                            <FormInput
                                                label={t('runs.dev_env.wizard.repo_url')}
                                                description={t('runs.dev_env.wizard.repo_url_description')}
                                                constraintText={t('runs.dev_env.wizard.repo_url_constraint')}
                                                placeholder={t('runs.dev_env.wizard.repo_url_placeholder')}
                                                control={control}
                                                name="repo_url"
                                                disabled={loading}
                                            />

                                            <FormInput
                                                label={t('runs.dev_env.wizard.repo_path')}
                                                description={t('runs.dev_env.wizard.repo_path_description')}
                                                constraintText={t('runs.dev_env.wizard.repo_path_constraint')}
                                                placeholder={t('runs.dev_env.wizard.repo_path_placeholder')}
                                                control={control}
                                                name="repo_path"
                                                disabled={loading}
                                            />
                                        </>
                                    )}
                                </SpaceBetween>
                            </Container>
                        ),
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
                                    name="config_yaml"
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
