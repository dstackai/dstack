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

const MailchimpSubscribe: React.FC<Props> = ({ className }) => {
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

    /*const onSubmit = async (data: FormValues) => {
        console.log(data);

        setLoading(true);
        try {
            await rest.mailchimpSubscribe(data);

            setLoading(false);
            setSuccess(true);
            reset();
        } catch (e) {
            setLoading(false);
            setSuccess(false);
        }

        await wait(3000);
        setSuccess(null);
    };*/

    return (
        <div className={cn(css.mailchimpSubscribeForm, className)}>
            <form
                action="https://dstack.us7.list-manage.com/subscribe/post?u=265ccb1949b39a23d350b177f&amp;id=8cfbe50714&amp;f_id=0034c4e4f0"
                target="_blank"
                method="post"
            >
                <Input
                    name='EMAIL'
                    placeholder="Type your email..."
                    className={css.input}
                    inputElementClassName={css.inputElement}
                    dimension="xxl"
                    disabled={loading}
                />

                <div className={css.button}>
                    <Button
                        type='submit'
                        showLoading={loading}
                        disabled={loading || Boolean(success)}
                        className={css.button}
                        appearance="black-fill"
                        dimension="xxl"
                    >
                        Subscribe
                    </Button>
                </div>
            </form>

            {/*{success === false && <div className={cn(css.label, 'error')}>Something went wrong</div>}
            {success && <div className={cn(css.label, 'success')}>Done</div>}
            {errors.email?.type === 'required' && <div className={cn(css.label, 'error')}>Please enter a valid email</div>}

            {errors.email?.type === 'email' && (
                <div className={cn(css.label, 'error')}>Please enter a valid email</div>
            )}*/}
        </div>
    );
};

export default MailchimpSubscribe;
