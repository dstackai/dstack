import React from 'react';
import { useTranslation } from 'react-i18next';
import { PublicApp } from 'PublicApp';
import { colorBackgroundHomeHeader } from '@cloudscape-design/design-tokens';

import { Box, Container, ContentLayout, Header, NavigateLink, SpaceBetween, Spinner } from 'components';

import { ROUTES } from 'routes';
import { useGetEntraInfoQuery, useGetGoogleInfoQuery, useGetOktaInfoQuery } from 'services/auth';

import { LoginByEntraID } from '../EntraID/LoginByEntraID';
import { LoginByGoogle } from '../LoginByGoogle';
import { LoginByOkta } from '../LoginByOkta';
import { LoginByTokenForm } from '../LoginByTokenForm';

export const SelfHostedLogin: React.FC<{ tokenOnly?: boolean }> = ({ tokenOnly = false }) => {
    const { t } = useTranslation();
    const { data: oktaData, isLoading: isLoadingOkta } = useGetOktaInfoQuery();
    const { data: entraData, isLoading: isLoadingEntra } = useGetEntraInfoQuery();
    const { data: googleData, isLoading: isLoadingGoogle } = useGetGoogleInfoQuery();

    const oktaEnabled = oktaData?.enabled;
    const entraEnabled = entraData?.enabled;
    const googleEnabled = googleData?.enabled;
    const isLoading = isLoadingOkta || isLoadingEntra || isLoadingGoogle;
    const hasSSO = oktaEnabled || entraEnabled || googleEnabled;
    const showTokenForm = tokenOnly || (!isLoading && !hasSSO);

    return (
        <PublicApp>
            <ContentLayout
                defaultPadding
                headerVariant="high-contrast"
                maxContentWidth={500}
                headerBackgroundStyle={colorBackgroundHomeHeader}
                header={
                    <Box variant="h1" padding={{ vertical: 'xxxl' }} textAlign="center">
                        {t('auth.sign_in_to_dstack')}
                    </Box>
                }
            >
                <Container
                    header={
                        <Box padding={{ bottom: 'xs' }}>
                            <Header variant="h2">{showTokenForm ? 'Sign in with a token' : t('common.login')}</Header>
                        </Box>
                    }
                >
                    <SpaceBetween size="l">
                        {showTokenForm && <LoginByTokenForm />}
                        {!tokenOnly && isLoading && <Spinner />}
                        {!tokenOnly && !isLoading && oktaEnabled && <LoginByOkta />}
                        {!tokenOnly && !isLoading && entraEnabled && <LoginByEntraID />}
                        {!tokenOnly && !isLoading && googleEnabled && <LoginByGoogle />}
                        {!isLoading && hasSSO && (
                            <NavigateLink href={tokenOnly ? ROUTES.BASE : ROUTES.AUTH.TOKEN}>
                                {tokenOnly ? t('auth.another_login_methods') : 'Sign in with a token'}
                            </NavigateLink>
                        )}
                    </SpaceBetween>
                </Container>
            </ContentLayout>
        </PublicApp>
    );
};
