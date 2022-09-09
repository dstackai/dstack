import React, { useCallback, useEffect, useState } from 'react';
import ConfirmModal, { Props as ConfirmationModalProps } from 'components/ConfirmModal';
import Input from 'components/Input';
import { useTranslation } from 'react-i18next';
import css from './index.module.css';

export interface Props extends Omit<ConfirmationModalProps, 'title' | 'confirmButtonProps' | 'cancelButtonProps' | 'ok'> {
    workflowCount?: number;
    ok: (clear: boolean) => void;
}

const ConfirmRestartRun: React.FC<Props> = ({ workflowCount, ok, ...props }) => {
    const { t } = useTranslation();
    const [clear, setClear] = useState(false);

    useEffect(() => {
        if (!props.show) setClear(false);
    }, [props.show]);

    const okHandle = useCallback<() => void>(() => {
        ok(clear);
    }, [clear]);

    return (
        <ConfirmModal title={t('restart')} confirmButtonProps={{ children: t('restart') }} ok={okHandle} {...props}>
            {t('confirm_messages.restart_run', { count: workflowCount })}

            <div className={css.clear}>
                <label className={css.label}>
                    <Input
                        className={css.checkbox}
                        type="checkbox"
                        checked={clear}
                        onChange={(event) => setClear(event.currentTarget.checked)}
                    />

                    {t('clear_output_artifacts')}
                </label>
            </div>
        </ConfirmModal>
    );
};

export default ConfirmRestartRun;
