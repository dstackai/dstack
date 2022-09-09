import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Button from 'components/Button';
import Modal from 'components/Modal';
import Artifacts from 'features/Artifacts';
import { ITableArtifactsCell } from 'components/Table/types';
import { ReactComponent as LayersIcon } from 'assets/icons/layers.svg';
import { artifactPathGetFolderName } from 'libs/artifacts';
import css from './index.module.css';

const ArtifactsCell: React.FC<{ children?: React.ReactNode } & ITableArtifactsCell> = ({ children, data }) => {
    const { t } = useTranslation();
    const [show, setShow] = useState<boolean>(false);

    if (!data.artifacts) return null;

    const [first, ...other] = data.artifacts;

    const onClick = (event: React.MouseEvent<HTMLButtonElement>) => {
        // For not open run table item collapsable list
        event.stopPropagation();
        setShow(true);
    };

    return (
        <div>
            {first && (
                <>
                    <Button
                        onClick={onClick}
                        className={css.button}
                        appearance="blue-transparent"
                        icon={<LayersIcon width={12} height={12} />}
                    >
                        {artifactPathGetFolderName(first)}
                        {Boolean(other.length) && <span>,...</span>}
                        {Boolean(other.length) && <span>+{other.length}</span>}
                    </Button>
                </>
            )}

            {children}

            {show && (
                //stopPropagation - For not open run table item collapsable list
                <Modal
                    className={css.modal}
                    dimension="m"
                    close={() => setShow(false)}
                    onClick={(event) => event.stopPropagation()}
                >
                    <Modal.Title>{t('artifact_other')}</Modal.Title>

                    <Modal.Content className={css.modalContent}>
                        <Artifacts {...data} />
                    </Modal.Content>
                </Modal>
            )}
        </div>
    );
};

export default ArtifactsCell;
