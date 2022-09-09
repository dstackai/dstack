import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button from 'components/Button';
import Input from 'components/Input';
import css from './index.module.css';

export interface Props extends ModalProps, Partial<Pick<IRun, 'run_name'>>, Partial<Pick<IJob, 'job_id'>> {
    workflowsCount?: number;
    ok: (abort: boolean) => void;
}

const ConfirmStop: React.FC<Props> = ({ close, ok, workflowsCount, run_name, job_id, ...props }) => {
    const { t } = useTranslation();
    const [abort, setAbort] = useState(false);

    return (
        <Modal close={close} {...props}>
            <Modal.Title>
                {(run_name || workflowsCount) && t('stopRun', { count: workflowsCount })}
                {job_id && t('stopJob')}
            </Modal.Title>

            <Modal.Content>
                {run_name && t('confirm_message_stop_run_with_name', { run_name })}
                {workflowsCount && t('confirm_message_stop_workflow_with_count', { count: workflowsCount })}
                {job_id && t('confirm_message_stop_job', { count: workflowsCount })}

                <div className={css.abort}>
                    <label className={css.label}>
                        <Input
                            className={css.checkbox}
                            type="checkbox"
                            checked={abort}
                            onChange={(event) => setAbort(event.currentTarget.checked)}
                        />

                        {(run_name || workflowsCount) && t('abort_workflow', { count: workflowsCount })}
                        {job_id && t('abort_job')}
                    </label>

                    <div className={css.description}>
                        {(run_name || workflowsCount) && t('stop_the_run_and_clear_all_the_data', { count: workflowsCount })}
                        {job_id && t('stop_the_job_and_clear_all_the_data')}
                    </div>
                </div>
            </Modal.Content>

            <Modal.Buttons>
                <Button appearance="blue-fill" onClick={() => ok(abort)}>
                    {(run_name || workflowsCount) && t('stopRun', { count: workflowsCount })}
                    {job_id && t('stopJob')}
                </Button>

                <Button appearance="gray-stroke" onClick={close}>
                    {t('cancel')}
                </Button>
            </Modal.Buttons>
        </Modal>
    );
};

export default ConfirmStop;
