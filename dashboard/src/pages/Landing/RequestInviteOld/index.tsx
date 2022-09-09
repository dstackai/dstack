import React, { useState } from 'react';
import cn from 'classnames';
import Input from 'components/Input';
import Button from 'components/Button';
import { useForm } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import * as yup from 'yup';
import { wait } from 'libs';
import rest from 'rest';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const schema = yup
    .object({
        email: yup.string().email().required(),
    })
    .required();

interface FormValues {
    email: string;
}

const RequestInvite: React.FC<Props> = ({ className }) => {
    const [loading, setLoading] = useState<boolean>(false);
    const [success, setSuccess] = useState<boolean | null>(null);

    const {
        register,
        handleSubmit,
        reset,
        formState: { errors },
    } = useForm<FormValues>({
        resolver: yupResolver(schema),
    });

    const onSubmit = async (data: FormValues) => {
        console.log(data);

        setLoading(true);
        try {
            await rest.accessRequest(data);

            setLoading(false);
            setSuccess(true);
            reset();
        } catch (e) {
            setLoading(false);
            setSuccess(false);
        }

        await wait(3000);
        setSuccess(null);
    };

    return (
        <div className={cn(css.requestInvite, className)}>
            <form onSubmit={handleSubmit(onSubmit)}>
                <Input
                    {...register('email')}
                    placeholder="Enter your email"
                    className={css.input}
                    inputElementClassName={css.inputElement}
                    disabled={loading}
                />

                <div className={css.button}>
                    <Button
                        type="submit"
                        appearance="violet-fill"
                        dimension="xxl"
                        showLoading={loading}
                        disabled={loading || Boolean(success)}
                    >
                        {success ? '👌 Request accepted' : 'Request access'}
                    </Button>
                </div>
            </form>

            {success === false && <div className={cn(css.label, 'error')}>Sorry, something went wrong. Please try again</div>}
            {success && <div className={cn(css.label, 'success')}>Your request is sent. We'll get back to you soon.</div>}
            {errors.email?.type === 'required' && <div className={cn(css.label, 'error')}>Email address is required</div>}

            {errors.email?.type === 'email' && (
                <div className={cn(css.label, 'error')}>Please, check the email address. Seems like it is incorrect. </div>
            )}

            {success === null && !errors.email && <div className={css.label}>Free forever. No credit card required.</div>}
        </div>
    );
};

export default RequestInvite;
