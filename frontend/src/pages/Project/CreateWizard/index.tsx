import React, { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';

import {
    Box,
    Container,
    FormCheckbox,
    FormField,
    FormInput,
    FormMultiselect,
    FormTiles,
    SpaceBetween,
    StatusIndicator,
    Wizard,
} from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';

import { getServerError } from '../../../libs';
import { useCreateProjectMutation } from '../../../services/project';
import { backendOptions } from './constants';

import { IProjectWizardForm } from './types';

import styles from './styles.module.scss';

const requiredFieldError = 'This is required field';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';
const numberFieldError = 'This is number field';

const projectValidationSchema = yup.object({
    project_name: yup
        .string()
        .required(requiredFieldError)
        .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    project_type: yup.string().required(requiredFieldError),
    backends: yup.array().when('project_type', {
        is: 'gpu_marketplace',
        then: yup.array().required(requiredFieldError),
    }),
    fleet_name: yup.string().when('enable_fleet', {
        is: true,
        then: yup
            .string()
            .required(requiredFieldError)
            .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    }),
    fleet_min_instances: yup.number().when('enable_fleet', {
        is: true,
        then: yup
            .number()
            .required(requiredFieldError)
            .typeError(numberFieldError)
            .min(1)
            .test('is-smaller-than-man', 'The minimum value must be less than the maximum value.', (value, context) => {
                const { fleet_max_instances } = context.parent;
                if (typeof fleet_max_instances !== 'number' || typeof value !== 'number') return true;
                return value <= fleet_max_instances;
            }),
    }),
    fleet_max_instances: yup.number().when('enable_fleet', {
        is: true,
        then: yup
            .number()
            .required(requiredFieldError)
            .typeError(numberFieldError)
            .min(1)
            .test('is-greater-than-min', 'The maximum value must be greater than the minimum value', (value, context) => {
                const { fleet_min_instances } = context.parent;
                if (typeof fleet_min_instances !== 'number' || typeof value !== 'number') return true;
                return value >= fleet_min_instances;
            }),
    }),
});

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error
const useYupValidationResolver = (validationSchema) =>
    useCallback(
        async (data: IProjectWizardForm) => {
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

export const CreateProjectWizard: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [createProject, { isLoading }] = useCreateProjectMutation();

    const loading = isLoading;

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: t('common.create', { text: t('navigation.project') }),
            href: ROUTES.PROJECT.ADD,
        },
    ]);

    const resolver = useYupValidationResolver(projectValidationSchema);
    const formMethods = useForm<IProjectWizardForm>({
        resolver,
        defaultValues: { enable_fleet: true, fleet_min_instances: 0 },
    });
    const { handleSubmit, control, watch, trigger, formState, getValues } = formMethods;
    const projectType = watch('project_type');
    const isEnabledFleet = watch('enable_fleet');

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.LIST);
    };

    const onSubmit = (data: IProjectWizardForm) => {
        console.log(data);
    };

    const validateFirstStep = async () => {
        return await trigger(['project_type', 'project_name']);
    };

    const validateSecondStep = async () => {
        if (projectType === 'gpu_marketplace') {
            return await trigger(['backends']);
        }

        return Promise.resolve(true);
    };

    const emptyValidator = async () => Promise.resolve(true);

    const onNavigate: WizardProps['onNavigate'] = ({ detail }) => {
        const stepValidators = [validateFirstStep, validateSecondStep, emptyValidator];

        if (detail.requestedStepIndex > activeStepIndex) {
            stepValidators[activeStepIndex]?.().then((isValid) => {
                if (isValid) {
                    setActiveStepIndex(detail.requestedStepIndex);
                }
            });
        } else {
            setActiveStepIndex(detail.requestedStepIndex);
        }
    };

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        if (!isValid) {
            return;
        }

        const { project_name } = getValues();

        const request = createProject({ project_name } as IProject).unwrap();

        request
            .then((data) => {
                pushNotification({
                    type: 'success',
                    content: t('projects.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(data.project_name));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <Wizard
                activeStepIndex={activeStepIndex}
                onNavigate={onNavigate}
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
                submitButtonText={t('projects.wizard.submit')}
                steps={[
                    {
                        title: 'Project name and type',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormInput
                                        label={t('projects.edit.project_name')}
                                        description={t('projects.edit.project_name_description')}
                                        control={control}
                                        name="project_name"
                                        disabled={loading}
                                    />

                                    <div>
                                        <FormField
                                            label={t('projects.edit.project_type')}
                                            description={t('projects.edit.project_type_description')}
                                            errorText={formState.errors.project_type?.message}
                                        >
                                            <FormTiles
                                                control={control}
                                                name="project_type"
                                                items={[
                                                    {
                                                        label: 'GPU marketplace',
                                                        description:
                                                            'Find the cheapest GPUs available in our marketplace. Enjoy $5 in free credits, and easily top up your balance with a credit card.',
                                                        value: 'gpu_marketplace',
                                                    },
                                                    {
                                                        label: 'Your cloud accounts',
                                                        description:
                                                            'Connect and manage your cloud accounts. dstack supports all major GPU cloud providers.',
                                                        value: 'own_cloud',
                                                    },
                                                ]}
                                            />
                                        </FormField>
                                    </div>
                                </SpaceBetween>
                            </Container>
                        ),
                    },
                    {
                        title: 'Backends',
                        content: (
                            <Container>
                                {projectType === 'gpu_marketplace' && (
                                    <FormMultiselect
                                        label={t('projects.edit.backends')}
                                        description={t('projects.edit.backends_description')}
                                        name="backends"
                                        control={control}
                                        options={backendOptions}
                                    />
                                )}

                                {projectType === 'own_cloud' && (
                                    <div className={styles.ownCloudInfo}>
                                        <Box>
                                            <StatusIndicator type="info" /> You will be able to configure own cloud after
                                            creating project
                                        </Box>
                                    </div>
                                )}
                            </Container>
                        ),
                    },
                    {
                        title: 'Fleets',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormCheckbox
                                        label={t('projects.edit.default_fleet')}
                                        description={t('projects.edit.default_fleet_description')}
                                        control={control}
                                        name="enable_fleet"
                                    />

                                    {isEnabledFleet && (
                                        <>
                                            <SpaceBetween direction="vertical" size="s">
                                                <div>
                                                    <StatusIndicator type="info" /> To create dev environments, submit tasks, or
                                                    run services, you need at least one fleet.
                                                </div>

                                                <div>
                                                    <StatusIndicator type="success" /> It's recommended to create it now, or you
                                                    can set it up manually later.
                                                </div>

                                                <div>
                                                    <StatusIndicator type="info" />
                                                    Don't worry, creating a fleet doesn’t necessarily create cloud instances.
                                                </div>
                                            </SpaceBetween>

                                            <FormInput
                                                label={t('projects.edit.fleet_name')}
                                                description={t('projects.edit.fleet_name_description')}
                                                control={control}
                                                name="fleet_name"
                                                disabled={loading}
                                            />

                                            <FormInput
                                                label={t('projects.edit.fleet_min_instances')}
                                                description={t('projects.edit.fleet_min_instances_description')}
                                                control={control}
                                                name="fleet_min_instances"
                                                disabled={loading}
                                                type="number"
                                            />

                                            <FormInput
                                                label={t('projects.edit.fleet_max_instances')}
                                                description={t('projects.edit.fleet_max_instances_description')}
                                                control={control}
                                                name="fleet_max_instances"
                                                disabled={loading}
                                                type="number"
                                            />
                                        </>
                                    )}
                                </SpaceBetween>
                            </Container>
                        ),
                    },
                ]}
            />
        </form>
    );
};
