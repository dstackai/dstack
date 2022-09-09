import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import * as yup from 'yup';
import { yupResolver } from '@hookform/resolvers/yup';
import { Link } from 'react-router-dom';
import AuthPage from 'components/AuthPage';
import Button from 'components/Button';
import { useSignUpMutation } from 'services/user';
import InputField from 'components/form/InputField';
import { getRouterModule, RouterModules } from 'route';
import { isErrorWithError } from 'libs';
import { useAppDispatch } from 'hooks';
import { setAuthToken } from 'App/slice';

const githubEnabled = process.env.GITHUB_ENABLED;

interface SignUpFormValues extends ISignUpRequestParams {
    confirm_password: string;
}

const schema = yup
    .object({
        user_name: yup.string().required(),
        email: yup.string().email().required(),
        password: yup.string().required(),
        confirm_password: yup
            .string()
            .required()
            .test('match-password', 'Passwords must match', (value, context) => value === context.parent.password),
    })
    .required();

const PasswordSignUp: React.FC = () => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const newRouter = getRouterModule(RouterModules.NEW_ROUTER);

    const [signUp, { isLoading, error, data }] = useSignUpMutation();

    const {
        register,
        handleSubmit,
        setError,
        formState: { errors },
    } = useForm<SignUpFormValues>({
        resolver: yupResolver(schema),
    });

    const submit = async (values: SignUpFormValues) => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { confirm_password, ...signUpData } = values;
        await signUp(signUpData);
    };

    useEffect(() => {
        if (error) {
            if ('status' in error && error.status === 400) {
                console.log(error);

                if (isErrorWithError(error)) {
                    setError('confirm_password', { type: 'custom', message: error.data.error });
                } else {
                    setError('confirm_password', { type: 'bad_credentials' });
                }
            } else setError('confirm_password', { type: 'server_error' });
        }
    }, [error]);

    useEffect(() => {
        if (data) {
            dispatch(setAuthToken(data.session));
        }
    }, [data]);

    return (
        <AuthPage>
            <form onSubmit={handleSubmit(submit)}>
                <AuthPage.Title>{t('sign_up_to_dstack')}</AuthPage.Title>

                <AuthPage.FieldContainer>
                    <InputField
                        dimension="m"
                        {...register('user_name')}
                        disabled={isLoading}
                        label={t('username')}
                        error={errors.user_name}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.FieldContainer>
                    <InputField
                        dimension="m"
                        {...register('email')}
                        disabled={isLoading}
                        label={t('email_address')}
                        error={errors.email}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.FieldContainer>
                    <InputField
                        dimension="m"
                        type="password"
                        {...register('password')}
                        disabled={isLoading}
                        label={t('password')}
                        error={errors.password}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.FieldContainer>
                    <InputField
                        dimension="m"
                        type="password"
                        {...register('confirm_password')}
                        disabled={isLoading}
                        label={t('confirm_password')}
                        error={errors.confirm_password}
                    />
                </AuthPage.FieldContainer>

                <AuthPage.ButtonsContainer>
                    <Button appearance="blue-fill" dimension="xl" type="submit">
                        {t('sign_up_to_dstack')}
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
                    {githubEnabled ? (
                        <span>
                            {t('i_wont_to_sign_up')}{' '}
                            <Link to={newRouter.buildUrl('auth.signup')}>{t('using_my_github_account')}</Link>
                        </span>
                    ) : (
                        <span>
                            {t('already_have_an_account')} <Link to={newRouter.buildUrl('auth.login')}>{t('sign_in')}</Link>
                        </span>
                    )}
                </AuthPage.SimpleText>
            </form>
        </AuthPage>
    );
};

export default PasswordSignUp;
