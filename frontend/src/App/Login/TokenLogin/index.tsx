import React from 'react';
import { useTranslation } from 'react-i18next';
import { colorBackgroundHomeHeader } from '@cloudscape-design/design-tokens';

import { Box, Container, ContentLayout, Header, NavigateLink, SpaceBetween } from 'components';

import { ROUTES } from 'routes';

import { LoginByTokenForm } from '../LoginByTokenForm';
import { SelfHostedLogin } from '../SelfHostedLogin';

export const TokenLogin: React.FC = () => {
    const { t } = useTranslation();

    if (process.env.UI_VERSION === 'sky') {
        return (
            <ContentLayout
                defaultPadding
                headerVariant="high-contrast"
                maxContentWidth={500}
                headerBackgroundStyle={colorBackgroundHomeHeader}
                header={
                    <Box variant="h1" padding={{ vertical: 'xxxl' }} textAlign="center">
                        {t('auth.sign_in_to_dstack_sky')}
                    </Box>
                }
            >
                <Container
                    header={
                        <Box padding={{ bottom: 'xs' }}>
                            <Header variant="h2">Sign in with a token</Header>
                        </Box>
                    }
                >
                    <SpaceBetween size="l">
                        <LoginByTokenForm />
                        <NavigateLink href={ROUTES.AUTH.LOGIN}>{t('auth.another_login_methods')}</NavigateLink>
                    </SpaceBetween>
                </Container>
            </ContentLayout>
        );
    }

    return <SelfHostedLogin tokenOnly />;
};
