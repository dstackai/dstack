import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useSearchParams } from 'react-router-dom';

import { Box, Button, Container, Header, Hotspot, Loader, Modal, SpaceBetween } from 'components';
import { PermissionGuard } from 'components/PermissionGuard';
import { HotspotIds } from 'layouts/AppLayout/TutorialPanel/constants';

import { useAppSelector, useBreadcrumbs, useNotifications } from 'hooks';
import { centsToFormattedString, getServerError, goToUrl } from 'libs';
import { ROUTES } from 'routes';
import {
    useGetUserBillingInfoQuery,
    useUserBillingCheckoutSessionMutation,
    useUserBillingPortalSessionMutation,
} from 'services/user';
import { GlobalUserRole } from 'types';

import { selectUserName } from 'App/slice';

import { CreditsHistory } from '../CreditsHistory';
import { Payments } from '../Payments';
import { MINIMAL_AMOUNT, PayForm } from './PayForm';

import { FormValues } from './PayForm/types';

export const Billing: React.FC = () => {
    const { t } = useTranslation();
    const [pushNotification] = useNotifications();
    const [searchParams, setSearchParams] = useSearchParams();
    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const userName = useAppSelector(selectUserName) ?? '';
    const params = useParams();
    const paramUserName = params.userName ?? '';

    const isCurrentUser = userName === paramUserName;

    const { data, isLoading } = useGetUserBillingInfoQuery({ username: paramUserName });
    const [billingCheckout, { isLoading: isLoadingBillingCheckout }] = useUserBillingCheckoutSessionMutation();
    const [billingPortalSession, { isLoading: isLoadingBillingPortalSession }] = useUserBillingPortalSessionMutation();

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
    ]);

    useEffect(() => {
        if (searchParams.get('payment_status') === 'success') {
            pushNotification({
                type: 'success',
                content: t('billing.payment_success_message'),
            });
            setSearchParams({});
        }
    }, []);

    const onSubmitPayment = ({ amount }: FormValues) => {
        billingCheckout({
            username: paramUserName,
            // Because the server needs amount value as cents
            amount: amount * 100,
        })
            .unwrap()
            .then((data) => goToUrl(data.url))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            })
            .finally(closeModal);
    };

    const makePaymentClick = () => {
        setShowPaymentModal(true);
    };

    const editPaymentMethod = () => {
        billingPortalSession({
            username: paramUserName,
        })
            .unwrap()
            .then((data) => goToUrl(data.url))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            })
            .finally(closeModal);
    };
    const closeModal = () => {
        setShowPaymentModal(false);
    };

    return (
        <SpaceBetween size="l">
            <Container header={<Header variant="h2">{t('billing.balance')}</Header>}>
                {isLoading && <Loader />}

                {data && (
                    <SpaceBetween size="m">
                        <Box variant="awsui-value-large">{centsToFormattedString(data?.balance ?? 0, '$')}</Box>

                        <SpaceBetween direction="horizontal" size="m">
                            {isCurrentUser && (
                                <Hotspot renderHotspot={!showPaymentModal} hotspotId={HotspotIds.ADD_TOP_UP_BALANCE}>
                                    <Button formAction="none" onClick={makePaymentClick}>
                                        {t('billing.top_up_balance')}
                                    </Button>
                                </Hotspot>
                            )}

                            {/* {data?.is_payment_method_attached && (
                                <Button formAction="none" onClick={editPaymentMethod} disabled={isLoadingBillingPortalSession}>
                                    {t('billing.edit_payment_method')}
                                </Button>
                            )} */}
                        </SpaceBetween>
                    </SpaceBetween>
                )}
            </Container>

            <Payments
                payments={data?.billing_history ?? []}
                isLoading={isLoading}
                tableHeaderContent={<Header variant="h2">{t('billing.billing_history')}</Header>}
            />

            <PermissionGuard allowedGlobalRoles={[GlobalUserRole.ADMIN]}>
                <CreditsHistory username={paramUserName} />
            </PermissionGuard>

            {showPaymentModal && (
                <Modal onDismiss={closeModal} visible closeAriaLabel="Close modal" header={t(`billing.top_up_balance`)}>
                    {data && (
                        <PayForm
                            isLoading={isLoadingBillingCheckout}
                            onCancel={closeModal}
                            onSubmit={onSubmitPayment}
                            defaultValues={{
                                // Todo решить с типама формы
                                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                                // @ts-ignore
                                amount: (data?.default_payment_amount / 100).toFixed(2) ?? MINIMAL_AMOUNT.toFixed(2),
                            }}
                        />
                    )}
                </Modal>
            )}
        </SpaceBetween>
    );
};
