import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ReactComponent as ExternalLinkIcon } from 'assets/icons/external-link.svg';
import Button from 'components/Button';
import Modal from 'components/Modal';
import { ITableAppsCell } from '../../types';
import css from './index.module.css';

export interface Props extends ITableAppsCell {
    children?: React.ReactNode;
}

const AppsCell: React.FC<Props> = ({ data: apps, asLink, linkProps = {} }) => {
    const { t } = useTranslation();
    const [showModal, setShowModal] = useState(false);
    const [first, ...other] = apps;

    const onClick = (event: React.MouseEvent<HTMLButtonElement | HTMLDivElement>) => {
        // For not open run table item collapsable list
        event.stopPropagation();
        setShowModal(true);
    };

    if (!first) return null;

    return (
        <div className={css.appsModal}>
            <ExternalLinkIcon className={css.icon} width={14} height={14} />

            <div className={css.app}>
                {asLink ? (
                    <a href={first.url} target="_blank" {...linkProps}>
                        {other.length ? first.app_name : t('open')}
                    </a>
                ) : (
                    <span className={css.gray}>{other.length ? first.app_name : t('open')}</span>
                )}
            </div>

            {Boolean(other.length) && (
                <>
                    <span>,...</span>
                    <Button onClick={onClick} className={css.otherCount} appearance="blue-transparent" dimension="s">
                        <span>+{other.length}</span>
                    </Button>
                </>
            )}

            {showModal && (
                //stopPropagation - For not open run table item collapsable list
                <Modal
                    className={css.modal}
                    dimension="m"
                    close={() => setShowModal(false)}
                    onClick={(event) => event.stopPropagation()}
                >
                    <Modal.Title>{t('app_other')}</Modal.Title>

                    <Modal.Content className={css.modalContent}>
                        {apps.map((app, index) => (
                            <div key={index}>
                                {asLink ? (
                                    <a href={app.url} target="_blank">
                                        {app.app_name}
                                    </a>
                                ) : (
                                    app.app_name
                                )}
                            </div>
                        ))}
                    </Modal.Content>
                </Modal>
            )}
        </div>
    );
};

export default AppsCell;
