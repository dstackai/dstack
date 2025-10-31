import React, { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import cn from 'classnames';
import * as yup from 'yup';
import { Box, Link, WizardProps } from '@cloudscape-design/components';
import { CardsProps } from '@cloudscape-design/components/cards';

import type { ToggleProps } from 'components';
import { Container, FormCodeEditor, FormField, FormInput, FormSelect, SpaceBetween, Toggle, Wizard } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useApplyRunMutation } from 'services/run';

import { OfferList } from 'pages/Offers/List';
import { convertMiBToGB, renderRange, round } from 'pages/Offers/List/helpers';

import { getRunSpecFromYaml } from './helpers/getRunSpecFromYaml';
import { useGenerateYaml } from './hooks/useGenerateYaml';

import { IRunEnvironmentFormValues } from './types';

import styles from './styles.module.scss';

const requiredFieldError = 'This is required field';
const namesFieldError = 'Only latin characters, dashes, and digits';

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

const envValidationSchema = yup.object({
    offer: yup.object().required(requiredFieldError),
    name: yup.string().matches(/^[a-z][a-z0-9-]{1,40}$/, namesFieldError),
    ide: yup.string().required(requiredFieldError),
    config_yaml: yup.string().required(requiredFieldError),
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

    const validateName = async () => {
        return await trigger(['name', 'ide']);
    };

    const validateConfig = async () => {
        return await trigger(['config_yaml']);
    };

    const emptyValidator = async () => Promise.resolve(true);

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateOffer, validateName, validateConfig, emptyValidator];

        if (reason === 'next') {
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

    const toggleDocker: ToggleProps['onChange'] = ({ detail }) => {
        setValue('docker', detail.checked);

        if (detail.checked) {
            setValue('python', '');
        } else {
            setValue('image', '');
        }
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
        } catch (error) {
            pushNotification({
                type: 'error',
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                content: error?.message,
            });

            window.scrollTo(0, 0);

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

    console.log(yaml);

    useEffect(() => {
        setValue('config_yaml', yaml);
    }, [yaml]);

    return (
        <form className={cn({ [styles.wizardForm]: activeStepIndex === 0 })} onSubmit={handleSubmit(onSubmit)}>
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

                                    <Toggle checked={formValues.docker} onChange={toggleDocker}>
                                        {t('runs.dev_env.wizard.docker')}
                                    </Toggle>

                                    <FormInput
                                        label={t('runs.dev_env.wizard.docker_image')}
                                        description={t('runs.dev_env.wizard.docker_image_description')}
                                        placeholder={t('runs.dev_env.wizard.docker_image_placeholder')}
                                        control={control}
                                        name="image"
                                        disabled={loading || !formValues.docker}
                                    />

                                    <FormInput
                                        label={t('runs.dev_env.wizard.python')}
                                        description={t('runs.dev_env.wizard.python_description')}
                                        placeholder={t('runs.dev_env.wizard.python_placeholder')}
                                        control={control}
                                        name="python"
                                        disabled={loading || formValues.docker}
                                    />

                                    <FormInput
                                        label={t('runs.dev_env.wizard.repo')}
                                        description={t('runs.dev_env.wizard.repo_description')}
                                        placeholder={t('runs.dev_env.wizard.repo_placeholder')}
                                        control={control}
                                        name="repo"
                                        disabled={loading}
                                    />

                                    <FormInput
                                        label={t('runs.dev_env.wizard.repo_local_path')}
                                        description={t('runs.dev_env.wizard.repo_local_path_description')}
                                        placeholder={t('runs.dev_env.wizard.repo_local_path_placeholder')}
                                        control={control}
                                        name="repo_local_path"
                                        disabled={loading}
                                    />
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
