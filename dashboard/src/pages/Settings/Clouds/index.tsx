import React, { useMemo, useState } from 'react';
import awsIcon from 'assets/icons/png/aws.png';
import TableContentSkeleton from 'components/TableContentSkeleton';
import columns from './columns';
import Button from 'components/Button';
import Table, { Cell, Row } from 'components/Table';
import { useClearAwsConfigMutation, useGetUserInfoQuery } from 'services/user';
import { useGetRegionsQuery, useGetSettingsQuery } from 'services/onDemand';
import { arrayToRecordByKeyName, getRegionByName } from 'libs';
import css from './index.module.css';
import { useTranslation } from 'react-i18next';
import ConfirmDeleteAWSConfig from './ConfirmDeleteAWSConfig';
import EditAWSConfigModal from './EditAWSConfigModal';

const mappedColumns = arrayToRecordByKeyName(columns, 'name');

const Clouds: React.FC = () => {
    const { t } = useTranslation();
    const [isShowEditModal, setShowEditModal] = useState<boolean>(false);
    const [isShowDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);

    const { data, isLoading } = useGetUserInfoQuery();
    const { data: regions } = useGetRegionsQuery();
    const [clearAWSConfig, { isLoading: isClearing }] = useClearAwsConfigMutation();
    const { data: settings } = useGetSettingsQuery();

    const { aws_access_key_id, aws_secret_access_key, aws_region, artifacts_s3_bucket } = data?.user_configuration ?? {};
    const hasConfig = !!(aws_access_key_id && aws_secret_access_key);

    const regionName = useMemo(() => {
        const region = getRegionByName(regions ?? [], aws_region ?? '');

        if (!region) return '';

        return `${region.title} (${region.location})`;
    }, [regions, aws_region]);

    const handleEdit = () => setShowEditModal(true);

    const deleteConfig = () => {
        clearAWSConfig();
        setShowDeleteConfirm(false);
    };

    const handleDelete = () => setShowDeleteConfirm(true);

    const handleAddAwsAccount = () => setShowEditModal(true);

    if (isLoading) return <TableContentSkeleton columns={columns} />;
    if (!data) return null;

    return (
        <div className={css.aws}>
            <Table className={css.table} columns={columns} withContextMenu>
                {hasConfig && (
                    <Row columns={columns} disabled={!settings?.enabled}>
                        <Cell
                            cell={{
                                ...mappedColumns['cloud'],
                                dataType: 'empty',
                            }}
                        >
                            <img src={awsIcon} alt="" width={28} height={28} />
                        </Cell>

                        <Cell
                            cell={{
                                ...mappedColumns['accessKey'],
                                dataType: 'text',
                                data: aws_access_key_id,
                            }}
                        />

                        <Cell
                            cell={{
                                ...mappedColumns['secretKey'],
                                dataType: 'text',
                                data: aws_secret_access_key,
                            }}
                        />

                        <Cell
                            cell={{
                                ...mappedColumns['region'],
                                dataType: 'text',
                                data: regionName,
                            }}
                        />

                        <Cell
                            cell={{
                                ...mappedColumns['artifactBucket'],
                                dataType: 'text',
                                data: artifacts_s3_bucket,
                            }}
                        />

                        <Row.ContextMenu autoHidden={false}>
                            <Row.EditButton onClick={handleEdit} />
                            <Row.DeleteButton disabled={isClearing} onClick={handleDelete} />
                        </Row.ContextMenu>
                    </Row>
                )}
            </Table>

            <Button appearance="blue-fill" className={css.addButton} onClick={handleAddAwsAccount} disabled={hasConfig}>
                {t('add_aws_account')}
            </Button>

            <ConfirmDeleteAWSConfig close={() => setShowDeleteConfirm(false)} ok={deleteConfig} show={isShowDeleteConfirm} />

            <EditAWSConfigModal config={data.user_configuration} show={isShowEditModal} close={() => setShowEditModal(false)} />
        </div>
    );
};

export default Clouds;
