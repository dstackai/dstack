import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, FormUI, Hotspot, SpaceBetween } from 'components';

import { HotspotIds } from '../../../../../layouts/AppLayout/TutorialPanel/constants';
import { AmountField } from '../components/AmountField';

import { FormValues, IProps } from './types';

export const MINIMAL_AMOUNT = 5;

export const PayForm: React.FC<IProps> = ({ defaultValues, isLoading, onCancel, onSubmit: onSubmitProp }) => {
    const { t } = useTranslation();

    const { handleSubmit, control } = useForm<FormValues>({
        defaultValues,
    });

    const onSubmit = (values: FormValues) => {
        onSubmitProp(values);
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            <FormUI
                actions={
                    <SpaceBetween direction="horizontal" size="xs">
                        <Button formAction="none" disabled={isLoading} variant="link" onClick={onCancel}>
                            {t('common.cancel')}
                        </Button>

                        <Hotspot hotspotId={HotspotIds.PAYMENT_CONTINUE_BUTTON}>
                            <Button loading={isLoading} disabled={isLoading} variant="primary">
                                {t('common.continue')}
                            </Button>
                        </Hotspot>
                    </SpaceBetween>
                }
            >
                <SpaceBetween size="l">
                    <AmountField
                        label={t('billing.payment_amount')}
                        description={t('billing.amount_description', { value: MINIMAL_AMOUNT.toFixed(2) })}
                        control={control}
                        name="amount"
                        inputMode="numeric"
                        step={0.01}
                        disabled={isLoading}
                        rules={{
                            required: t('validation.required'),

                            min: {
                                value: MINIMAL_AMOUNT,
                                message: t('billing.min_amount_error_message', { value: MINIMAL_AMOUNT }),
                            },
                        }}
                    />
                </SpaceBetween>
            </FormUI>
        </form>
    );
};
