import React from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import Modal, { Props as ModalProps } from 'components/Modal';
import Artifacts from 'features/Artifacts';
import css from './index.module.css';
import { useAppDispatch, useAppSelector } from 'hooks';
import { closeArtifacts, selectArtifacts, selectParams } from './slice';

export type Props = Omit<ModalProps, 'show' | 'close'>;

const ArtifactsModal: React.FC<Props> = ({ className, ...props }) => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();
    const artifacts = useAppSelector(selectArtifacts);
    const params = useAppSelector(selectParams);

    const closeHandle = () => dispatch(closeArtifacts());

    if (!artifacts || !params) return null;

    return (
        <Modal
            className={cn(css.modal, className)}
            dimension="m"
            show
            close={closeHandle}
            onClick={(event) => event.stopPropagation()}
            {...props}
        >
            <Modal.Title>{t('artifact_other')}</Modal.Title>

            <Modal.Content className={css.modalContent}>
                <Artifacts artifacts={artifacts} {...params} />
            </Modal.Content>
        </Modal>
    );
};

export default ArtifactsModal;
