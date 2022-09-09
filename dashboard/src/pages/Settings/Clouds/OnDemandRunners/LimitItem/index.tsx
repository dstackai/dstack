import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Cell, Row } from 'components/Table';
import Button from 'components/Button';
import { ITableColumn } from 'components/Table/types';
import Input from 'components/Input';
import AvailabilityIssuesTooltip from 'components/AvailabilityIssuesTooltip';
import ConfirmDeleteLimit from './ConfirmDeleteLimit';
import { ReactComponent as PencilIcon } from 'assets/icons/pencil.svg';
import { ReactComponent as CheckIcon } from 'assets/icons/check.svg';
import { ReactComponent as CloseIcon } from 'assets/icons/close.svg';
import { ReactComponent as DeleteOutlineIcon } from 'assets/icons/delete-outline.svg';
import { ReactComponent as AlertIcon } from 'assets/icons/alert.svg';
import { getResourcesString } from 'libs/runner';
import { limitMaximumToString } from 'libs/onDemand';
import { arrayToRecordByKeyName, getRegionByName } from 'libs';
import { useDeleteLimitMutation, useGetRegionsQuery, useSetLimitMutation } from 'services/onDemand';
import columns from '../columns';
import css from './index.module.css';
import cn from 'classnames';

const mappedColumns: { [key: string]: ITableColumn } = arrayToRecordByKeyName(columns, 'name');

export interface Props {
    limit: ILimit;
    disabledEdit?: boolean;
}

const RunnerItem: React.FC<Props> = ({ disabledEdit, limit }) => {
    const { t } = useTranslation();
    const [isEditing, setIsEditing] = useState<boolean>(false);
    const [maximumState, setMaximumState] = useState<string>('');
    const [showConfirmDelete, setShowConfirmDelete] = useState<boolean>(false);
    const { data: regions } = useGetRegionsQuery();
    const [deleteLimit, { isLoading: isDeleting }] = useDeleteLimitMutation();
    const [setLimit, { isLoading: isSetting }] = useSetLimitMutation();

    const regionTitle: string = useMemo(() => {
        if (!regions) return limit.region_name;
        const region = getRegionByName(regions, limit.region_name);

        return region ? `${region.title}/${region.location}` : '';
    }, [regions]);

    useEffect(() => {
        if (!isEditing) setMaximumState(limitMaximumToString(limit.maximum));
    }, [limit.maximum]);

    const confirmDelete = () => {
        const { region_name, instance_type, purchase_type } = limit;
        deleteLimit({ region_name, instance_type, purchase_type });
    };

    const editing = () => {
        setMaximumState(limitMaximumToString(limit.maximum));
        setIsEditing(true);
    };

    const cancelEditing = () => {
        setMaximumState(limitMaximumToString(limit.maximum));
        setIsEditing(false);
    };

    const onChangeMaximum = (event: React.ChangeEvent<HTMLInputElement>) => {
        let { value } = event.currentTarget;
        value = value.replace(/\D/gi, '');
        setMaximumState(value);
    };

    const submitMaximum = () => {
        const maximum = parseInt(maximumState, 10);
        const { region_name, instance_type, purchase_type } = limit;

        if (isNaN(maximum)) return;

        setLimit({
            region_name,
            instance_type,
            purchase_type,
            maximum,
        })
            .unwrap()
            .then(() => {
                setIsEditing(false);
            });
    };

    return (
        <React.Fragment>
            <Row className={css.row}>
                <Cell
                    cell={{
                        ...mappedColumns['region'],
                        dataType: 'text',
                        data: regionTitle,
                    }}
                />

                <Cell
                    cell={{
                        ...mappedColumns['instance_type'],
                        dataType: 'text',
                        data: limit.instance_type,
                    }}
                />

                <Cell
                    cell={{
                        ...mappedColumns['resources'],
                        dataType: 'text',
                        data: limit.resources ? getResourcesString(limit.resources) : '',
                    }}
                />

                <Cell cell={{ ...mappedColumns['purchase_type'], dataType: 'text', data: t(limit.purchase_type) }} />

                <Cell
                    cell={{
                        ...mappedColumns['estimated_price'],
                        dataType: 'text',
                        data: '',
                    }}
                />

                <Cell
                    cell={{
                        ...mappedColumns['maximum'],
                        dataType: 'text',
                        data: '',
                    }}
                >
                    <div className={css.maximum}>
                        {!isEditing && (
                            <React.Fragment>
                                <div className={css.value}>{limit.maximum}</div>

                                {!disabledEdit && (
                                    <Button
                                        className={css.button}
                                        appearance="gray-transparent"
                                        displayAsRound
                                        icon={<PencilIcon />}
                                        onClick={editing}
                                    />
                                )}
                            </React.Fragment>
                        )}

                        {isEditing && (
                            <React.Fragment>
                                <Input
                                    className={css.input}
                                    value={maximumState}
                                    onChange={onChangeMaximum}
                                    disabled={isSetting}
                                />

                                <Button
                                    disabled={!maximumState || isSetting}
                                    type="submit"
                                    className={cn(css.button, css.applyButton)}
                                    appearance="gray-transparent"
                                    displayAsRound
                                    icon={<CheckIcon />}
                                    onClick={submitMaximum}
                                />

                                <Button
                                    className={css.button}
                                    disabled={isSetting}
                                    appearance="gray-transparent"
                                    displayAsRound
                                    icon={<CloseIcon />}
                                    onClick={cancelEditing}
                                />
                            </React.Fragment>
                        )}
                    </div>
                </Cell>

                <Cell
                    cell={{
                        ...mappedColumns['in_use'],
                        dataType: 'text',
                        data: '',
                    }}
                >
                    <div className={css.iconContainer}>
                        {limit.availability_issues_at && (
                            <AvailabilityIssuesTooltip
                                availabilityIssues={[
                                    { timestamp: limit.availability_issues_at, message: limit.availability_issues_message },
                                ]}
                            >
                                <AlertIcon className={css.alertIcon} />
                            </AvailabilityIssuesTooltip>
                        )}
                    </div>

                    {!disabledEdit && (
                        <Button
                            className={css.delete}
                            onClick={() => setShowConfirmDelete(true)}
                            disabled={isDeleting}
                            icon={<DeleteOutlineIcon />}
                            appearance="gray-transparent"
                        />
                    )}
                </Cell>
            </Row>

            {showConfirmDelete && <ConfirmDeleteLimit close={() => setShowConfirmDelete(false)} ok={confirmDelete} />}
        </React.Fragment>
    );
};

export default RunnerItem;
