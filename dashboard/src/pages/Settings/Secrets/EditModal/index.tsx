import React, { useMemo } from 'react';
import * as yup from 'yup';
import { yupResolver } from '@hookform/resolvers/yup';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button from 'components/Button';
import InputField from 'components/form/InputField';
import { useAddSecretMutation, useUpdateSecretMutation, useDeleteSecretMutation } from 'services/secrets';
import css from './index.module.css';

export interface Props extends ModalProps {
    secret?: ISecret;
}

type FormValues = AddedEmptyString<Omit<ISecret, 'secret_id'>>;

const schema = yup
    .object({
        secret_name: yup.string().required(),
        secret_value: yup.string().required(),
    })
    .required();

const EditModal: React.FC<Props> = ({ close, secret, ...props }) => {
    const { t } = useTranslation();

    const [addSecret, { isLoading: isAddLoading }] = useAddSecretMutation();
    const [updateSecret, { isLoading: isUpdateLoading }] = useUpdateSecretMutation();
    const [deleteSecret, { isLoading: isDeleteLoading }] = useDeleteSecretMutation();

    const isEditing = !!secret?.secret_id;

    const isLoading = useMemo<boolean>(() => {
        return isAddLoading || isUpdateLoading || isDeleteLoading;
    }, [isAddLoading, isUpdateLoading, isDeleteLoading]);

    const {
        register,
        handleSubmit,
        formState: { errors },
    } = useForm<FormValues>({
        resolver: yupResolver(schema),
        defaultValues: secret,
    });

    const submitHandle = async (values: FormValues) => {
        try {
            if (isEditing) {
                const { secret_id } = secret;
                await updateSecret({ ...values, secret_id });
            } else await addSecret(values);
            close();
        } catch (err) {
            console.log(err);
        }
    };

    const deleteSecretHandle = async () => {
        if (!secret) return;
        try {
            const { secret_id } = secret;
            await deleteSecret({ secret_id });
            close();
        } catch (err) {
            console.log(err);
        }
    };

    return (
        <Modal className={css.modal} close={close} {...props}>
            <form className={css.form} onSubmit={handleSubmit(submitHandle)}>
                <input autoComplete="off" name="hidden" type="text" style={{ display: 'none' }} />
                <Modal.Title>{t(isEditing ? 'edit_secret' : 'add_secret')}</Modal.Title>

                <Modal.Content>
                    <InputField
                        {...register('secret_name')}
                        className={css.field}
                        label={t('key')}
                        error={errors.secret_name}
                        autoComplete="secret_name"
                        disabled={isLoading}
                    />

                    <InputField
                        {...register('secret_value')}
                        className={css.field}
                        label={t('value')}
                        type="password"
                        error={errors.secret_value}
                        autoComplete="new-password"
                        disabled={isLoading}
                    />
                </Modal.Content>

                <Modal.Buttons>
                    <Button appearance="blue-fill" type="submit" disabled={isLoading}>
                        {t(isEditing ? 'save' : 'add')}
                    </Button>

                    <Button appearance="gray-stroke" onClick={close} disabled={isLoading}>
                        {t('cancel')}
                    </Button>

                    {isEditing && (
                        <Button
                            className={css.delete}
                            appearance="red-stroke"
                            onClick={deleteSecretHandle}
                            disabled={isLoading}
                        >
                            {t('delete_secret')}
                        </Button>
                    )}
                </Modal.Buttons>
            </form>
        </Modal>
    );
};

export default EditModal;
