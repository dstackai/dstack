import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import AuthPage from 'components/AuthPage';
import Button from 'components/Button';
import InputField from 'components/form/InputField';
import { useForm } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import * as yup from 'yup';
import { useLoginMutation } from 'services/user';
import { useAppDispatch } from 'hooks';
import { setAuthToken } from 'App/slice';
import GithubAuthButton from 'components/GithubAuthButton';
import { createUrlWithBase } from 'libs';
import css from './index.module.css';

const githubEnabled = process.env.GITHUB_ENABLED;

const schema = yup
    .object({
        user_name: yup.string().required(),
        password: yup.string().required(),
    })
    .required();

type FormValues = ILoginRequestParams;

const SignIn: React.FC = () => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();

    const [login, { isLoading, error, data }] = useLoginMutation();

    const {
        register,
        handleSubmit,
        formState: { errors },
        setError,
    } = useForm<FormValues>({
        resolver: yupResolver(schema),
    });

    useEffect(() => {
        if (error) {
            if ('status' in error && error.status === 401) setError('password', { type: 'bad_credentials' });
            else setError('password', { type: 'server_error' });
        }
    }, [error]);

    useEffect(() => {
        if (data) {
            dispatch(setAuthToken(data.session));
        }
    }, [data]);

    const submit = (values: FormValues) => login(values);

    return (
        <AuthPage>
            <AuthPage.Title>{t('sign_in_to_dstack')}</AuthPage.Title>

            {githubEnabled && (
                <React.Fragment>
                    <AuthPage.ButtonsContainer>
                        <GithubAuthButton url={createUrlWithBase(process.env.API_URL, '/users/github/register')}>
                            {t('sign_in_with_gitHub')}
                        </GithubAuthButton>
                    </AuthPage.ButtonsContainer>

                    <AuthPage.SimpleText dimension="l" className={css.or}>
                        <span>{t('or_sign_in_using_your_email')}</span>
                    </AuthPage.SimpleText>
                </React.Fragment>
            )}

            <form className={css.form} onSubmit={handleSubmit(submit)}>
                <AuthPage.FieldContainer>
                    <InputField
                        {...register('user_name')}
                        dimension="m"
                        label={t('username')}
                        error={errors.user_name}
                        disabled={isLoading}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.FieldContainer>
                    <InputField
                        {...register('password')}
                        dimension="m"
                        label={t('password')}
                        error={errors.password}
                        type="password"
                        disabled={isLoading}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.ButtonsContainer>
                    <Button type="submit" dimension="xl" className={css.submit} appearance="blue-fill" disabled={isLoading}>
                        {t('sign_in_to_dstack')}
                    </Button>
                </AuthPage.ButtonsContainer>
            </form>

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
        </AuthPage>
    );
};

export default SignIn;
