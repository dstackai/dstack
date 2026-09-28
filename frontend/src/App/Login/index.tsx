import React from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate } from 'react-router-dom';
import { product } from 'product';
import { PublicApp } from 'PublicApp';
import { colorBackgroundHomeHeader } from '@cloudscape-design/design-tokens';

import { Box, Container, ContentLayout, Header, Link, NavigateLink, SpaceBetween, Spinner } from 'components';

import { useAppSelector } from 'hooks';
import { ROUTES } from 'routes';
import { useGetAuthProvidersQuery } from 'services/auth';
import { useGetUserDataQuery } from 'services/user';

import { Loading } from 'App/Loading';
import { selectAuthToken } from 'App/slice';

import { LoginByEntraID } from './EntraID/LoginByEntraID';
import { LoginByGithub } from './LoginByGithub';
import { LoginByGoogle } from './LoginByGoogle';
import { LoginByOkta } from './LoginByOkta';
import { LoginByTokenForm } from './LoginByTokenForm';

const providerButtons = {
    github: LoginByGithub,
    okta: LoginByOkta,
    entra: LoginByEntraID,
    google: LoginByGoogle,
};

export const Login: React.FC<{ tokenOnly?: boolean }> = ({ tokenOnly = false }) => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const localStorageIsAvailable = 'localStorage' in window;
    const {
        currentData: userData,
        error,
        isFetching,
    } = useGetUserDataQuery({ token }, { skip: tokenOnly || !token || !localStorageIsAvailable });
    const { data: providers, isLoading } = useGetAuthProvidersQuery(undefined, { skip: tokenOnly });
    const enabledProviders = Object.entries(providerButtons).filter(([name]) =>
        providers?.some((provider) => provider.name === name && provider.enabled),
    );
    const showTokenForm = tokenOnly || (!isLoading && enabledProviders.length === 0);

    if (!tokenOnly && token && localStorageIsAvailable) {
        if (isFetching && !userData) return <Loading />;
        if (userData?.username && !error) return <Navigate replace to={ROUTES.RUNS.LIST} />;
    }

    const content = (
        <ContentLayout
            defaultPadding
            headerVariant="high-contrast"
            maxContentWidth={500}
            headerBackgroundStyle={colorBackgroundHomeHeader}
            header={
                <Box variant="h1" padding={{ vertical: 'xxxl' }} textAlign="center">
                    {t('auth.welcome', { product: product.name })}
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
                    {!tokenOnly &&
                        !isLoading &&
                        enabledProviders.map(([name, ProviderButton]) => <ProviderButton key={name} />)}
                    {!tokenOnly && !isLoading && enabledProviders.length > 0 && product.isSky && (
                        <Box color="text-body-secondary" fontSize="body-s">
                            By continuing, you agree to the{' '}
                            <Link href="https://dstack.ai/terms/" target="_blank" external>
                                Terms
                            </Link>{' '}
                            and{' '}
                            <Link href="https://dstack.ai/privacy/" target="_blank" external>
                                Privacy policy
                            </Link>
                        </Box>
                    )}
                    {tokenOnly ? (
                        <NavigateLink href={ROUTES.BASE}>{t('auth.another_login_methods')}</NavigateLink>
                    ) : (
                        !showTokenForm && <NavigateLink href={ROUTES.AUTH.TOKEN}>Sign in with a token</NavigateLink>
                    )}
                </SpaceBetween>
            </Container>
        </ContentLayout>
    );
    return product.hasPresets ? content : <PublicApp>{content}</PublicApp>;
};
