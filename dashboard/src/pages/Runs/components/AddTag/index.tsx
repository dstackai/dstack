import React, { useEffect, useState } from 'react';
import Modal, { Props as ModalProps } from 'components/Modal';
import InputField from 'components/form/InputField';
import { useTranslation } from 'react-i18next';
import { useAddMutation } from 'services/tags';
import Button from 'components/Button';
import css from './index.module.css';

export interface Props extends ModalProps, Omit<TAddTagRequestParams, 'tag_name'> {}

const AddTagModal: React.FC<Props> = ({ close, repo_user_name, repo_name, run_name, ...props }) => {
    const { t } = useTranslation();
    const [tagName, setTagName] = useState('');

    useEffect(() => {
        if (!props.show) setTagName('');
    }, [props.show]);

    const [addTag, { isLoading, isSuccess, isError }] = useAddMutation();

    useEffect(() => {
        if (isSuccess) close();
    }, [isSuccess]);

    const onSubmit = () => {
        addTag({
            repo_user_name,
            repo_name,
            run_name,
            tag_name: tagName,
        });
    };

    return (
        <Modal close={close} {...props}>
            <Modal.Title>{t('add_tag')}</Modal.Title>

            <Modal.Content>
                <div className={css.label}>{t('enter_unique_tagname')}</div>
                <InputField
                    value={tagName}
                    onChange={(e) => setTagName(e.target.value)}
                    error={isError ? 'Error' : undefined}
                />
            </Modal.Content>

            <Modal.Buttons>
                <Button disabled={isLoading} appearance="blue-fill" onClick={onSubmit}>
                    {t('save_tag')}
                </Button>

                <Button disabled={isLoading} appearance="gray-stroke" onClick={close}>
                    {t('cancel')}
                </Button>
            </Modal.Buttons>
        </Modal>
    );
};

export default AddTagModal;
