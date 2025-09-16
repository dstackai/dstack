import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';
import { TilesProps } from '@cloudscape-design/components/tiles';

import {
    // Box,
    Cards,
    Container,
    FormCards,
    // FormCheckbox,
    FormField,
    FormInput,
    // FormMultiselect,
    FormTiles,
    KeyValuePairs,
    SpaceBetween,
    // StatusIndicator,
    Wizard,
} from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useGetBackendBaseTypesQuery, useGetBackendTypesQuery } from 'services/backend';
import { useCreateWizardProjectMutation } from 'services/project';

import { projectTypeOptions } from './constants';

import { IProjectWizardForm } from './types';

// import styles from './styles.module.scss';

const requiredFieldError = 'This is required field';
const minOneLengthError = 'Need to choose one or more';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';
// const numberFieldError = 'This is number field';

const projectValidationSchema = yup.object({
    project_name: yup
        .string()
        .required(requiredFieldError)
        .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    project_type: yup.string().required(requiredFieldError),
    backends: yup.array().when('project_type', {
        is: 'gpu_marketplace',
        then: yup.array().min(1, minOneLengthError).required(requiredFieldError),
    }),
    // fleet_name: yup.string().when('enable_fleet', {
    //     is: true,
    //     then: yup
    //         .string()
    //         .required(requiredFieldError)
    //         .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    // }),
    // fleet_min_instances: yup.number().when('enable_fleet', {
    //     is: true,
    //     then: yup
    //         .number()
    //         .required(requiredFieldError)
    //         .typeError(numberFieldError)
    //         .min(1)
    //         .test('is-smaller-than-man', 'The minimum value must be less than the maximum value.', (value, context) => {
    //             const { fleet_max_instances } = context.parent;
    //             if (typeof fleet_max_instances !== 'number' || typeof value !== 'number') return true;
    //             return value <= fleet_max_instances;
    //         }),
    // }),
    // fleet_max_instances: yup.number().when('enable_fleet', {
    //     is: true,
    //     then: yup
    //         .number()
    //         .required(requiredFieldError)
    //         .typeError(numberFieldError)
    //         .min(1)
    //         .test('is-greater-than-min', 'The maximum value must be greater than the minimum value', (value, context) => {
    //             const { fleet_min_instances } = context.parent;
    //             if (typeof fleet_min_instances !== 'number' || typeof value !== 'number') return true;
    //             return value >= fleet_min_instances;
    //         }),
    // }),
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
    const [createProject, { isLoading }] = useCreateWizardProjectMutation();
    const { data: backendBaseTypesData, isLoading: isBackendBaseTypesLoading } = useGetBackendBaseTypesQuery();
    const { data: backendTypesData, isLoading: isBackendTypesLoading } = useGetBackendTypesQuery();

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

    const backendBaseOptions = useMemo(() => {
        if (!backendBaseTypesData) {
            return [];
        }

        return backendBaseTypesData.map((b: TProjectBackend) => ({
            label: b,
            value: b,
        }));
    }, [backendBaseTypesData]);

    const backendOptions = useMemo(() => {
        if (!backendTypesData) {
            return [];
        }

        return backendTypesData.map((b: TProjectBackend) => ({
            label: b,
            value: b,
        }));
    }, [backendTypesData]);

    const resolver = useYupValidationResolver(projectValidationSchema);
    const formMethods = useForm<IProjectWizardForm>({
        resolver,
        defaultValues: { project_type: 'gpu_marketplace', enable_fleet: true, fleet_min_instances: 0 },
    });
    const { handleSubmit, control, watch, trigger, formState, getValues, setValue, setError } = formMethods;
    const formValues = watch();

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.LIST);
    };

    const getFormValuesForServer = (): TCreateWizardProjectParams => {
        const { project_name, backends, project_type } = getValues();

        return {
            project_name,
            config: {
                base_backends: project_type === 'gpu_marketplace' ? (backends ?? []) : [],
            },
        };
    };

    const validateNameAndType = async () => {
        try {
            const yupValidationResult = await trigger(['project_type', 'project_name']);

            const serverValidationResult = await createProject({
                ...getFormValuesForServer(),
                dry: true,
            })
                .unwrap()
                .then(() => true)
                .catch((error) => {
                    const errorDetail = (error?.data?.detail ?? []) as { msg: string; code: string }[];
                    const projectExist = errorDetail.some(({ code }) => code === 'resource_exists');

                    if (projectExist) {
                        setError('project_name', { type: 'custom', message: 'Project with this name already exists' });
                    }

                    return false;
                });

            return yupValidationResult && serverValidationResult;
        } catch (e) {
            console.log(e);
            return false;
        }
    };

    const validateBackends = async () => {
        if (formValues['project_type'] === 'gpu_marketplace') {
            return await trigger(['backends']);
        }

        return Promise.resolve(true);
    };

    const emptyValidator = async () => Promise.resolve(true);

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateNameAndType, validateBackends, emptyValidator];

        if (reason === 'next') {
            stepValidators[activeStepIndex]?.().then((isValid) => {
                if (isValid) {
                    setActiveStepIndex(requestedStepIndex);
                }
            });
        } else {
            setActiveStepIndex(requestedStepIndex);
        }
    };

    const onNavigateHandler: WizardProps['onNavigate'] = ({ detail: { requestedStepIndex, reason } }) => {
        onNavigate({ requestedStepIndex, reason });
    };

    const onChangeProjectType = (backendType: string) => {
        if (backendType === 'gpu_marketplace') {
            setValue(
                'backends',
                backendBaseOptions.map((b: { value: string }) => b.value),
            );
        } else {
            trigger(['backends']).catch(console.log);
        }
    };

    const onChangeProjectTypeHandler: TilesProps['onChange'] = ({ detail: { value } }) => {
        onChangeProjectType(value);
    };

    useEffect(() => {
        if (backendBaseOptions?.length) {
            onChangeProjectType(formValues.project_type);
        }
    }, [backendBaseOptions]);

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        if (!isValid) {
            return;
        }

        const request = createProject(getFormValuesForServer()).unwrap();

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

    const onSubmit = () => {
        if (activeStepIndex < 2) {
            onNavigate({ requestedStepIndex: activeStepIndex + 1, reason: 'next' });
        } else {
            onSubmitWizard().catch(console.log);
        }
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
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
                submitButtonText={t('projects.wizard.submit')}
                steps={[
                    {
                        title: 'Name and type',
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
                                                items={projectTypeOptions}
                                                onChange={onChangeProjectTypeHandler}
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
                                <FormField
                                    label={t('projects.edit.backends')}
                                    description={
                                        formValues['project_type'] === 'gpu_marketplace'
                                            ? t('projects.edit.base_backends_description')
                                            : t('projects.edit.backends_description')
                                    }
                                    errorText={formState.errors.backends?.message}
                                />

                                <br />

                                {formValues['project_type'] === 'gpu_marketplace' && (
                                    <FormCards
                                        control={control}
                                        name="backends"
                                        items={backendBaseOptions}
                                        selectionType="multi"
                                        loading={isBackendBaseTypesLoading}
                                        cardDefinition={{
                                            header: (item) => item.label,
                                        }}
                                        cardsPerRow={[{ cards: 1 }, { minWidth: 400, cards: 2 }, { minWidth: 800, cards: 3 }]}
                                    />
                                )}

                                {formValues['project_type'] === 'own_cloud' && (
                                    <Cards
                                        // selectionType="multi"
                                        // selectedItems={backendOptions}
                                        loading={isBackendTypesLoading}
                                        items={backendOptions}
                                        cardDefinition={{
                                            header: (item) => item.label,
                                        }}
                                        cardsPerRow={[{ cards: 1 }, { minWidth: 400, cards: 2 }, { minWidth: 800, cards: 3 }]}
                                    />
                                )}
                            </Container>
                        ),
                    },
                    // {
                    //     title: 'Fleets',
                    //     content: (
                    //         <Container>
                    //             <SpaceBetween direction="vertical" size="l">
                    //                 <FormCheckbox
                    //                     label={t('projects.edit.default_fleet')}
                    //                     description={t('projects.edit.default_fleet_description')}
                    //                     control={control}
                    //                     name="enable_fleet"
                    //                 />
                    //
                    //                 {formValues['enable_fleet'] && (
                    //                     <>
                    //                         <SpaceBetween direction="vertical" size="s">
                    //                             <div>
                    //                                 <StatusIndicator type="info" /> To create dev environments, submit tasks, or
                    //                                 run services, you need at least one fleet.
                    //                             </div>
                    //
                    //                             <div>
                    //                                 <StatusIndicator type="success" /> It's recommended to create it now, or you
                    //                                 can set it up manually later.
                    //                             </div>
                    //
                    //                             <div>
                    //                                 <StatusIndicator type="info" />
                    //                                 Don't worry, creating a fleet doesn’t necessarily create cloud instances.
                    //                             </div>
                    //                         </SpaceBetween>
                    //
                    //                         <FormInput
                    //                             label={t('projects.edit.fleet_name')}
                    //                             description={t('projects.edit.fleet_name_description')}
                    //                             control={control}
                    //                             name="fleet_name"
                    //                             disabled={loading}
                    //                         />
                    //
                    //                         <FormInput
                    //                             label={t('projects.edit.fleet_min_instances')}
                    //                             description={t('projects.edit.fleet_min_instances_description')}
                    //                             control={control}
                    //                             name="fleet_min_instances"
                    //                             disabled={loading}
                    //                             type="number"
                    //                         />
                    //
                    //                         <FormInput
                    //                             label={t('projects.edit.fleet_max_instances')}
                    //                             description={t('projects.edit.fleet_max_instances_description')}
                    //                             control={control}
                    //                             name="fleet_max_instances"
                    //                             disabled={loading}
                    //                             type="number"
                    //                         />
                    //                     </>
                    //                 )}
                    //             </SpaceBetween>
                    //         </Container>
                    //     ),
                    // },
                    {
                        title: 'Summary',
                        content: (
                            <Container>
                                <KeyValuePairs
                                    items={[
                                        {
                                            label: t('projects.edit.project_name'),
                                            value: formValues['project_name'],
                                        },
                                        {
                                            label: t('projects.edit.project_type'),
                                            value: projectTypeOptions.find(({ value }) => value === formValues['project_type'])
                                                ?.label,
                                        },
                                        {
                                            label: t('projects.edit.backends'),
                                            value:
                                                formValues['project_type'] === 'gpu_marketplace'
                                                    ? (formValues['backends'] ?? []).join(', ')
                                                    : 'The backends can be configured with your own cloud credentials in the project settings after the project is created.',
                                        },
                                    ]}
                                />
                            </Container>
                        ),
                    },
                ]}
            />
        </form>
    );
};
