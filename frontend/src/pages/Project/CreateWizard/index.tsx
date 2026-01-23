import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { isNil } from 'lodash';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';
import { TilesProps } from '@cloudscape-design/components/tiles';

import {
    Cards,
    Container,
    FormCards,
    FormField,
    FormInput,
    FormTiles,
    FormToggle,
    InfoLink,
    KeyValuePairs,
    SpaceBetween,
    Wizard,
} from 'components';

import { useBreadcrumbs, useConfirmationDialog, useHelpPanel, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useGetBackendBaseTypesQuery, useGetBackendTypesQuery } from 'services/backend';
import { useApplyFleetMutation } from 'services/fleet';
import { useCreateWizardProjectMutation } from 'services/project';

import { FleetFormFields } from '../../Fleets/Add/FleetFormFields';
import {
    getMaxInstancesValidator,
    getMinInstancesValidator,
    idleDurationValidator,
} from '../../Fleets/Add/FleetFormFields/constants';
import { DEFAULT_FLEET_INFO } from '../constants';
import { useYupValidationResolver } from '../hooks/useYupValidationResolver';
import { projectTypeOptions } from './constants';

import { IProjectWizardForm } from './types';

const requiredFieldError = 'This is required field';
const minOneLengthError = 'Need to choose one or more';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';

const fleetStepIndex = 2;

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
    fleet: yup.object().shape({
        min_instances: yup.number().when('enable_default', {
            is: true,
            then: getMinInstancesValidator('max_instances'),
        }),
        max_instances: yup.number().when('enable_default', {
            is: true,
            then: getMaxInstancesValidator('min_instances'),
        }),
        idle_duration: yup.string().when('enable_default', {
            is: true,
            then: idleDurationValidator,
        }),
    }),
});

export const CreateProjectWizard: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [openHelpPanel] = useHelpPanel();
    const [createProject, { isLoading }] = useCreateWizardProjectMutation();
    const [applyFleet, { isLoading: isApplyingFleet }] = useApplyFleetMutation();
    const { data: backendBaseTypesData, isLoading: isBackendBaseTypesLoading } = useGetBackendBaseTypesQuery();
    const { data: backendTypesData, isLoading: isBackendTypesLoading } = useGetBackendTypesQuery();

    const [openConfirmationDialog] = useConfirmationDialog();

    const loading = isLoading || isApplyingFleet;

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: t('common.create_wit_text', { text: t('navigation.project') }),
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
        defaultValues: {
            project_type: 'gpu_marketplace',
            fleet: {
                enable_default: true,
                min_instances: 0,
                idle_duration: '5m',
            },
        },
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

    const getFormValuesForFleetApplying = (): IApplyFleetPlanRequestRequest => {
        const {
            fleet: { min_instances, max_instances, idle_duration, name },
        } = getValues();

        return {
            plan: {
                spec: {
                    configuration: {
                        ...(name ? { name } : {}),
                        nodes: {
                            min: min_instances,
                            ...(max_instances ? { max: max_instances } : {}),
                        },
                        ...(idle_duration ? { idle_duration } : {}),
                    },
                    profile: {},
                },
            },
            force: false,
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

    const validateFleet = async () => {
        return await trigger(['fleet.enable_default', 'fleet.min_instances', 'fleet.max_instances', 'fleet.idle_duration']);
    };

    const emptyValidator = async () => Promise.resolve(true);

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateNameAndType, validateBackends, validateFleet, emptyValidator];

        if (reason === 'next') {
            stepValidators[activeStepIndex]?.().then((isValid) => {
                if (isValid) {
                    if (activeStepIndex === fleetStepIndex && formValues?.['fleet']['min_instances'] > 0) {
                        openConfirmationDialog({
                            title: 'Are sure want to set min instances above than 0?',
                            content: null,
                            onConfirm: () => setActiveStepIndex(requestedStepIndex),
                        });
                    } else {
                        setActiveStepIndex(requestedStepIndex);
                    }
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

        const { fleet } = getValues();

        if (!isValid) {
            return;
        }

        const request = createProject(getFormValuesForServer()).unwrap();

        request
            .then(async (data) => {
                if (fleet.enable_default) {
                    await applyFleet({
                        projectName: data.project_name,
                        ...getFormValuesForFleetApplying(),
                    }).unwrap();
                }

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
        if (activeStepIndex < 3) {
            onNavigate({ requestedStepIndex: activeStepIndex + 1, reason: 'next' });
        } else {
            onSubmitWizard().catch(console.log);
        }
    };

    const getDefaultFleetSummary = () => {
        const summaryFields: Array<keyof IProjectWizardForm['fleet']> = [
            'name',
            'min_instances',
            'max_instances',
            'idle_duration',
        ];

        const result: string[] = [];

        summaryFields.forEach((fieldName) => {
            if (!isNil(formValues?.fleet?.[fieldName])) {
                result.push(`${t(`fleets.edit.${fieldName}`)}: ${formValues['fleet'][fieldName]}`);
            }
        });

        return result.join(', ');
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
                        title: 'Settings',
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
                                            header: (item: { label: string }) => item.label,
                                        }}
                                        cardsPerRow={[{ cards: 1 }, { minWidth: 400, cards: 2 }, { minWidth: 800, cards: 3 }]}
                                    />
                                )}
                            </Container>
                        ),
                    },
                    {
                        title: 'Fleets',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormToggle
                                        toggleLabel={<strong>{t('projects.edit.default_fleet')}</strong>}
                                        constraintText={t('projects.edit.default_fleet_description')}
                                        toggleInfo={<InfoLink onFollow={() => openHelpPanel(DEFAULT_FLEET_INFO)} />}
                                        control={control}
                                        name="fleet.enable_default"
                                    />

                                    {formValues['fleet']['enable_default'] && (
                                        <FleetFormFields<IProjectWizardForm>
                                            control={control}
                                            disabledAllFields={loading}
                                            fieldNamePrefix="fleet"
                                        />
                                    )}
                                </SpaceBetween>
                            </Container>
                        ),
                    },
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
                                        ...(formValues['fleet']['enable_default']
                                            ? [
                                                  {
                                                      label: 'Default fleet',
                                                      value: getDefaultFleetSummary(),
                                                  },
                                              ]
                                            : []),
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
