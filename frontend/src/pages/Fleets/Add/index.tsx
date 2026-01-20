import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { isNil } from 'lodash';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';

import { Container, FormSelect, KeyValuePairs, SpaceBetween, Wizard } from 'components';

import { useBreadcrumbs, useConfirmationDialog, useNotifications } from 'hooks';
import { useProjectFilter } from 'hooks/useProjectFilter';
import { ROUTES } from 'routes';
import { useApplyFleetMutation } from 'services/fleet';

import { useYupValidationResolver } from 'pages/Project/hooks/useYupValidationResolver';

import { getMaxInstancesValidator, getMinInstancesValidator, idleDurationValidator } from './FleetFormFields/constants';
import { FleetFormFields } from './FleetFormFields';

import { IFleetWizardForm } from './types';

const requiredFieldError = 'This is required field';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';

const fleetStepIndex = 1;

const fleetValidationSchema = yup.object({
    project_name: yup
        .string()
        .required(requiredFieldError)
        .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
    min_instances: getMinInstancesValidator('max_instances'),
    max_instances: getMaxInstancesValidator('min_instances'),
    idle_duration: idleDurationValidator,
});

export const FleetAdd: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [openConfirmationDialog] = useConfirmationDialog();
    const [applyFleet, { isLoading: isApplyingFleet }] = useApplyFleetMutation();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const resolver = useYupValidationResolver(fleetValidationSchema);
    const { projectOptions } = useProjectFilter({ localStorePrefix: 'add-fleet-page' });

    const loading = isApplyingFleet;

    const formMethods = useForm<IFleetWizardForm>({
        resolver,
        defaultValues: {
            min_instances: 0,
            idle_duration: '5m',
        },
    });

    const { handleSubmit, control, clearErrors, trigger, watch, getValues } = formMethods;
    const formValues = watch();

    const getFormValuesForFleetApplying = (): IApplyFleetPlanRequestRequest => {
        const { min_instances, max_instances, idle_duration, name } = getValues();

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
            text: t('navigation.fleets'),
            href: ROUTES.FLEETS.LIST,
        },

        {
            text: t('common.create_wit_text', { text: t('navigation.fleet') }),
            href: ROUTES.FLEETS.ADD,
        },
    ]);

    const validateName = async () => {
        return await trigger(['project_name']);
    };

    const validateFleet = async () => {
        return await trigger(['min_instances', 'max_instances', 'idle_duration']);
    };

    const emptyValidator = async () => Promise.resolve(true);

    const onNavigate = ({
        requestedStepIndex,
        reason,
    }: {
        requestedStepIndex: number;
        reason: WizardProps.NavigationReason;
    }) => {
        const stepValidators = [validateName, validateFleet, emptyValidator];

        if (reason === 'next') {
            stepValidators[activeStepIndex]?.().then((isValid) => {
                if (isValid) {
                    if (activeStepIndex === fleetStepIndex && formValues?.['min_instances'] > 0) {
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
        navigate(ROUTES.FLEETS.LIST);
    };

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        const { project_name } = getValues();

        if (!isValid) {
            return;
        }

        clearErrors();

        const request = applyFleet({
            projectName: project_name,
            ...getFormValuesForFleetApplying(),
        }).unwrap();

        request
            .then((data) => {
                pushNotification({
                    type: 'success',
                    content: t('fleets.create.success_notification'),
                });

                navigate(ROUTES.FLEETS.DETAILS.FORMAT(data.project_name, data.id));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error ?? error }),
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

    const getDefaultFleetSummary = () => {
        const summaryFields: Array<keyof IFleetWizardForm> = ['name', 'min_instances', 'max_instances', 'idle_duration'];

        const result: string[] = [];

        summaryFields.forEach((fieldName) => {
            if (!isNil(formValues?.[fieldName])) {
                result.push(`${t(`fleets.edit.${fieldName}`)}: ${formValues?.[fieldName]}`);
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
                        title: 'Project',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormSelect
                                        label={t('projects.edit.project_name')}
                                        control={control}
                                        name="project_name"
                                        options={projectOptions}
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
                                    <FleetFormFields<IFleetWizardForm> control={control} disabledAllFields={loading} />
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
                                            label: 'Default fleet',
                                            value: getDefaultFleetSummary(),
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
