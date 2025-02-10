import React from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Button, Container, ContentLayout, FormInput, FormUI, Header, SpaceBetween } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError, isResponseServerError, isResponseServerFormFieldError } from 'libs';
import { getFieldErrorFromServerResponse } from 'libs/form';
import { ROUTES } from 'routes';
import { useAddUserPaymentMutation } from 'services/user';

import { AmountField } from '../../Billing/components/AmountField';

import { TFormValue } from './types';
import { FieldPath } from 'react-hook-form/dist/types/path';

export const Add: React.FC = () => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const navigate = useNavigate();
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const [createPayment, { isLoading }] = useAddUserPaymentMutation();

    const formMethods = useForm<TFormValue>();

    const { handleSubmit, control, setError, clearErrors } = formMethods;

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('billing.title'),
            href: ROUTES.USER.BILLING.LIST.FORMAT(paramUserName),
        },
        {
            text: t('users.manual_payments.title'),
            href: ROUTES.USER.BILLING.LIST.FORMAT(paramUserName),
        },
        {
            text: t('common.add'),
            href: ROUTES.USER.BILLING.ADD_PAYMENT.FORMAT(paramUserName),
        },
    ]);

    const onSubmit = ({ value, ...data }: TFormValue) => {
        clearErrors();

        createPayment({
            ...data,
            // Convert to cents
            value: value * 100,
            username: paramUserName,
        })
            .unwrap()
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('users.manual_payments.create.success_notification'),
                });

                navigate(ROUTES.USER.DETAILS.FORMAT(paramUserName));
            })
            .catch((errorResponse) => {
                const errorRequestData = errorResponse?.data;

                if (isResponseServerError(errorRequestData)) {
                    errorRequestData.detail.forEach((error) => {
                        if (isResponseServerFormFieldError(error)) {
                            const { fieldNamePath, message } = getFieldErrorFromServerResponse(error);

                            setError(fieldNamePath as FieldPath<TFormValue>, { type: 'custom', message });
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
                        content: t('common.server_error', { error: getServerError(errorResponse) }),
                    });
                }
            });
    };

    const onCancel = () => {
        navigate(ROUTES.USER.DETAILS.FORMAT(paramUserName));
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{t('users.manual_payments.add_payment')}</Header>}>
            <form onSubmit={handleSubmit(onSubmit)}>
                <FormUI
                    actions={
                        <SpaceBetween direction="horizontal" size="xs">
                            <Button formAction="none" disabled={isLoading} variant="link" onClick={onCancel}>
                                {t('common.cancel')}
                            </Button>

                            <Button loading={isLoading} disabled={isLoading} variant="primary">
                                {t('common.save')}
                            </Button>
                        </SpaceBetween>
                    }
                >
                    <SpaceBetween size="l">
                        <Container>
                            <SpaceBetween size="l">
                                <AmountField
                                    label={t('users.manual_payments.edit.value')}
                                    description={t('users.manual_payments.edit.value_description')}
                                    control={control}
                                    name="value"
                                    disabled={isLoading}
                                    rules={{
                                        required: t('validation.required'),
                                    }}
                                />

                                <FormInput
                                    label={t('users.manual_payments.edit.description')}
                                    description={t('users.manual_payments.edit.description_description')}
                                    control={control}
                                    name="description"
                                    disabled={isLoading}
                                />
                            </SpaceBetween>
                        </Container>
                    </SpaceBetween>
                </FormUI>
            </form>
        </ContentLayout>
    );
};
