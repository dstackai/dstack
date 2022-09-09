import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import cn from 'classnames';
import Button from 'components/Button';
import Switcher from 'components/Switcher';
import Table from 'components/Table';
import TableContentSkeleton from 'components/TableContentSkeleton';
import LimitItem from './LimitItem';
import AddLimit from './AddLimit';
import ConfirmDisabledOnDemand from './ConfirmDisabledOnDemand';
import { useGetSettingsQuery, useGetLimitsQuery, useUpdateSettingsMutation, useGetRegionsQuery } from 'services/onDemand';
import columns from './columns';
import css from './index.module.css';

export interface Props {
    className?: string;
}

const OnDemandRunners: React.FC<Props> = ({ className }) => {
    const { t } = useTranslation();
    const [isEnabled, setIsEnabled] = useState<boolean>(false);
    const [showAdd, setShowAdd] = useState<boolean>(false);
    const [showConfirmDisable, setShowConfirmDisable] = useState<boolean>(false);

    const { data: settings, isLoading: isLoadingSettings } = useGetSettingsQuery();
    const { data: limits, isLoading: isLoadingLimits } = useGetLimitsQuery();
    const { isLoading: isLoadingRegions } = useGetRegionsQuery();
    const [updateSettings] = useUpdateSettingsMutation();

    useEffect(() => {
        if (settings && isEnabled !== settings.enabled) setIsEnabled(settings.enabled);
    }, [settings]);

    const onChangeIsEnabled = (event: React.ChangeEvent<HTMLInputElement>) => {
        const { checked } = event.currentTarget;

        if (checked) {
            setIsEnabled(checked);
            updateSettings({ enabled: checked });
        } else setShowConfirmDisable(true);
    };

    const confirmDisable = () => {
        setIsEnabled(false);
        updateSettings({ enabled: false });
        setShowConfirmDisable(false);
    };

    if (isLoadingSettings || isLoadingLimits || isLoadingRegions)
        return (
            <section className={cn(css.section, className)}>
                <TableContentSkeleton rowsCount={4} />
            </section>
        );

    return (
        <section className={cn(css.section, className)}>
            <div className={css.enablingSwitcher}>
                <div className={css.label}>{t('on_demand_runners')}</div>

                {settings && (
                    <Switcher onChange={onChangeIsEnabled} value="enabled" checked={isEnabled} className={css.switcher} />
                )}
            </div>

            <Table className={cn(css.table)} columns={columns}>
                {limits &&
                    limits.map((l, index) => (
                        <LimitItem limit={l} key={index} disabledEdit={!isEnabled || settings?.read_only} />
                    ))}
            </Table>

            <Button
                disabled={!isEnabled || settings?.read_only}
                className={css.addLimit}
                appearance={'blue-transparent'}
                onClick={() => setShowAdd(true)}
            >
                + {t('add_limit')}
            </Button>

            {showAdd && <AddLimit close={() => setShowAdd(false)} />}

            {showConfirmDisable && <ConfirmDisabledOnDemand close={() => setShowConfirmDisable(false)} ok={confirmDisable} />}
        </section>
    );
};

export default OnDemandRunners;
