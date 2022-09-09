import React from 'react';
import { useTranslation } from 'react-i18next';
import Modal from 'components/Modal';
import { useAppDispatch, useAppSelector } from 'hooks';
import { selectApps, selectOpenModal, closeModal } from './slice';

const AppsModal: React.FC = () => {
    const { t } = useTranslation();
    const dispatch = useAppDispatch();

    const apps = useAppSelector(selectApps);
    const showModal = useAppSelector(selectOpenModal);

    const closeHandle = () => dispatch(closeModal());

    if (!apps) return null;

    return (
        <Modal show={showModal} dimension="m" close={closeHandle} onClick={(event) => event.stopPropagation()}>
            <Modal.Title>{t('app_other')}</Modal.Title>

            <Modal.Content>
                {apps.map((app, index) => (
                    <div key={index}>
                        <a href={app.url} target="_blank">
                            {app.app_name}
                        </a>
                    </div>
                ))}
            </Modal.Content>
        </Modal>
    );
};

export default AppsModal;
