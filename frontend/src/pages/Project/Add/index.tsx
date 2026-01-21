import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { isNil } from 'lodash';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';

import { Container, FormInput, FormToggle, InfoLink, KeyValuePairs, SpaceBetween, Wizard } from 'components';

import { useBreadcrumbs, useConfirmationDialog, useHelpPanel, useNotifications } from 'hooks';
import { isResponseServerError, isResponseServerFormFieldError } from 'libs';
import { ROUTES } from 'routes';
import { useApplyFleetMutation } from 'services/fleet';
import { useCreateProjectMutation } from 'services/project';

import { FleetFormFields } from 'pages/Fleets/Add/FleetFormFields';
import {
    getMaxInstancesValidator,
    getMinInstancesValidator,
    idleDurationValidator,
} from 'pages/Fleets/Add/FleetFormFields/constants';

import { DEFAULT_FLEET_INFO } from '../constants';
import { useYupValidationResolver } from '../hooks/useYupValidationResolver';

import { IProjectForm } from '../Form/types';
import { FieldPath } from 'react-hook-form/dist/types/path';

const requiredFieldError = 'This is required field';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';

const fleetStepIndex = 1;

const projectValidationSchema = yup.object({
    project_name: yup
        .string()
        .required(requiredFieldError)
        .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    is_public: yup.boolean(),
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

export const ProjectAdd: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [openConfirmationDialog] = useConfirmationDialog();
    const [openHelpPanel] = useHelpPanel();
    const [createProject, { isLoading }] = useCreateProjectMutation();
    const [applyFleet, { isLoading: isApplyingFleet }] = useApplyFleetMutation();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const resolver = useYupValidationResolver(projectValidationSchema);

    const loading = isLoading || isApplyingFleet;

    const formMethods = useForm<IProjectForm>({
        resolver,
        defaultValues: {
            is_public: false,
            fleet: {
                enable_default: true,
                min_instances: 0,
                idle_duration: '5m',
            },
        },
    });

    const { handleSubmit, control, setError, clearErrors, trigger, watch, getValues } = formMethods;
    const formValues = watch();

    const getFormValuesForServer = (): IProjectCreateRequestParams => {
        const { project_name, is_public } = getValues();

        return {
            project_name,
            is_public,
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

    const validateNameAndType = async () => {
        return await trigger(['project_name', 'is_public']);
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
        const stepValidators = [validateNameAndType, validateFleet, emptyValidator];

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

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.LIST);
    };

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        const { fleet } = getValues();

        if (!isValid) {
            return;
        }

        clearErrors();

        const request = createProject(getFormValuesForServer()).unwrap();

        request
            .then(async (data) => {
                pushNotification({
                    type: 'success',
                    content: t('projects.create.success_notification'),
                });

                if (fleet.enable_default) {
                    await applyFleet({
                        projectName: data.project_name,
                        ...getFormValuesForFleetApplying(),
                    }).unwrap();
                }

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(data.project_name));
            })
            .catch((error) => {
                const errorRequestData = error?.data;

                if (isResponseServerError(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isResponseServerFormFieldError(error)) {
                            setError(error.loc.join('.') as FieldPath<IProjectForm>, { type: 'custom', message: error.msg });
                        } else {
                            pushNotification({
                                type: 'error',
                                content: t('common.server_error', { error: error.msg }),
                            });
                        }
                    });
                } else {
                    pushNotification({
                        type: 'error',
                        content: t('common.server_error', { error: error?.error ?? error }),
                    });
                }
            });
    };

    const onSubmit = () => {
        if (activeStepIndex < 2) {
            onNavigate({ requestedStepIndex: activeStepIndex + 1, reason: 'next' });
        } else {
            onSubmitWizard().catch(console.log);
        }
    };

    const getDefaultFleetSummary = () => {
        const summaryFields: Array<keyof IProjectForm['fleet']> = ['name', 'min_instances', 'max_instances', 'idle_duration'];

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
                        title: 'Name and public',
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

                                    <FormToggle
                                        label={t('projects.edit.is_public')}
                                        toggleDescription={t('projects.edit.is_public_description')}
                                        control={control}
                                        name="is_public"
                                        disabled={loading}
                                    />
                                </SpaceBetween>
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
                                        <FleetFormFields<IProjectForm>
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
