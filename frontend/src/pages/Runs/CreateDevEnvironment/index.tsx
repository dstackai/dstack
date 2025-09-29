import React, { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import * as yup from 'yup';
import { WizardProps } from '@cloudscape-design/components';
import { CardsProps } from '@cloudscape-design/components/cards';

import { Code, Container, FormCodeEditor, FormField, FormInput, KeyValuePairs, SpaceBetween, Wizard } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';

import { OfferList } from 'pages/Offers/List';

import { IRunEnvironmentFormValues } from './types';

const requiredFieldError = 'This is required field';
const namesFieldError = 'Only latin characters, dashes, underscores, and digits';

const envValidationSchema = yup.object({
    offer: yup.object().required(requiredFieldError),
    name: yup
        .string()
        .required(requiredFieldError)
        .matches(/^[a-zA-Z0-9-_]+$/, namesFieldError),
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
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [activeStepIndex, setActiveStepIndex] = useState(0);
    const [selectedOffers, setSelectedOffers] = useState<IGpu[]>([]);

    const loading = false;

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
        defaultValues: {},
    });
    const { handleSubmit, control, trigger, setValue, watch, formState } = formMethods;
    const formValues = watch();

    const onCancelHandler = () => {
        navigate(ROUTES.RUNS.LIST);
    };

    const validateOffer = async () => {
        return await trigger(['offer']);
    };

    const validateName = async () => {
        return await trigger(['name']);
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
        setValue('offer', newSelectedOffers?.[0] ?? null);
    };

    const onSubmitWizard = async () => {
        const isValid = await trigger();

        if (!isValid) {
            return;
        }

        // TODO send request
    };

    const onSubmit = () => {
        if (activeStepIndex < 3) {
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
                submitButtonText={t('runs.dev_env.wizard.submit')}
                steps={[
                    {
                        title: 'Select Offer',
                        content: (
                            <>
                                <FormField
                                    label={t('runs.dev_env.wizard.offer')}
                                    description={t('runs.dev_env.wizard.offer_description')}
                                />
                                <OfferList
                                    selectionType="single"
                                    withSearchParams={false}
                                    selectedItems={selectedOffers}
                                    onSelectionChange={onChangeOffer}
                                />
                                <FormField errorText={formState.errors.offer?.message} />
                            </>
                        ),
                    },

                    {
                        title: 'Name',
                        content: (
                            <Container>
                                <SpaceBetween direction="vertical" size="l">
                                    <FormInput
                                        label={t('runs.dev_env.wizard.name')}
                                        description={t('runs.dev_env.wizard.name_description')}
                                        control={control}
                                        name="name"
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
                                    label={t('runs.dev_env.wizard.config')}
                                    description={t('runs.dev_env.wizard.config_description')}
                                    name="config_yaml"
                                    language="yaml"
                                    loading={loading}
                                    editorContentHeight={600}
                                />
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
                                            label: t('runs.dev_env.wizard.offer'),
                                            value: formValues['offer']?.name,
                                        },
                                        {
                                            label: t('runs.dev_env.wizard.name'),
                                            value: formValues['name'],
                                        },
                                        {
                                            label: t('runs.dev_env.wizard.config'),
                                            value: <Code>{formValues['config_yaml']}</Code>,
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
