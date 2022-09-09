import React from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { ReactComponent as EmailIcon } from 'assets/icons/email.svg';
import GithubAuthButton from 'components/GithubAuthButton';
import Button from 'components/Button';
import AuthPage from 'components/AuthPage';
import { createUrlWithBase } from 'libs';
import { getRouterModule, RouterModules } from 'route';

const SignUp: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    const toSignUpForm = () => navigate(newRouter.buildUrl('auth.signup-email'));

    return (
        <AuthPage>
            <AuthPage.Title>{t('sign_up_to_dstack')}</AuthPage.Title>

            <AuthPage.ButtonsContainer>
                <GithubAuthButton url={createUrlWithBase(process.env.API_URL, '/users/github/register')}>
                    {t('sign_up_via_gitHub')}
                </GithubAuthButton>
            </AuthPage.ButtonsContainer>

            <AuthPage.ButtonsContainer>
                <Button appearance="blue-fill" dimension="xl" onClick={toSignUpForm} icon={<EmailIcon />}>
                    {t('sign_up_with_email')}
                </Button>
            </AuthPage.ButtonsContainer>

            <AuthPage.SimpleText>
                {t('agree_to_')}{' '}
                <a
                    href={'https://dstackai.notion.site/dstack-ai-Terms-of-Service-a21bff613836482ea3629a93e3aa1581'}
                    target={'_blank'}
                >
                    {t('Terms of service')}
                </a>{' '}
                <br />
                {t('and')}{' '}
                <a
                    href={'https://dstackai.notion.site/dstack-ai-Privacy-Policy-1dc143f6e52147228441cc4e2100cd78'}
                    target={'_blank'}
                >
                    {t('Privacy policy')}
                </a>
            </AuthPage.SimpleText>

            <AuthPage.Divider />

            <AuthPage.SimpleText dimension="l">
                {t('already_have_an_account')} <Link to={newRouter.buildUrl('auth.login')}>{t('sign_in')}</Link>{' '}
            </AuthPage.SimpleText>
        </AuthPage>
    );
};

export default SignUp;
