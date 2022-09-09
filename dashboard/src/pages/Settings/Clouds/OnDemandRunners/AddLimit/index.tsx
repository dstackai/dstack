import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { yupResolver } from '@hookform/resolvers/yup';
import * as yup from 'yup';
import Modal, { Props as ModalProps } from 'components/Modal';
import Button from 'components/Button';
import InputField from 'components/form/InputField';
import SelectField from 'components/form/SelectField';
import { instanceTypesToSelectFieldOptions, regionsToSelectFieldOptions } from 'libs';
import { useSetLimitMutation, useGetInstanceTypesQuery, useGetRegionsQuery } from 'services/onDemand';
import { useGetUserInfoQuery } from 'services/user';
import css from './index.module.css';

export interface Props extends ModalProps {
    asd?: string;
}

type FormValues = AddedEmptyString<ISetLimitRequestParams>;

const PURCHASE_TYPES: TPurchaseType[] = ['spot', 'on-demand'];

const schema = yup
    .object({
        region_name: yup.string().required(),
        instance_type: yup.string().required(),
        purchase_type: yup.string().required(),
        maximum: yup.number().min(1).required(),
    })
    .required();

const Limit: React.FC<Props> = ({ close, ...props }) => {
    const { t } = useTranslation();

    const {
        register,
        setValue,
        handleSubmit,
        watch,
        formState: { errors },
    } = useForm<FormValues>({
        resolver: yupResolver(schema),
    });

    const { region_name: formRegionName, instance_type: formInstanceType, purchase_type: formPurchaseType } = watch();
    const { data: regions, isLoading: isLoadingRegions } = useGetRegionsQuery();
    const { data: user, isLoading: isLoadingUserInfo } = useGetUserInfoQuery();
    const { data: instanceTypes, isLoading: isLoadingInstanceTypes } = useGetInstanceTypesQuery(
        {
            region_name: formRegionName,
        },
        {
            skip: !formRegionName,
        },
    );

    const [setLimit, { isLoading: isSetting }] = useSetLimitMutation();

    const supportedPurchaseTypes: Set<TPurchaseType> = useMemo(() => {
        if (formInstanceType && instanceTypes) {
            const typeObject = instanceTypes.find((i) => i.instance_type === formInstanceType);

            if (typeObject) {
                const supported = new Set(typeObject.purchase_types);

                if (formPurchaseType && !supported.has(formPurchaseType)) setValue('purchase_type', '');

                return supported;
            }
        }

        return new Set<TPurchaseType>(PURCHASE_TYPES);
    }, [instanceTypes, formInstanceType]);

    useEffect(() => {
        const userRegion = user?.user_configuration?.aws_region;
        if (userRegion && !formRegionName) setValue('region_name', userRegion);
    }, [user]);

    const submit = async (values: FormValues) => {
        try {
            await setLimit(values as ISetLimitRequestParams).unwrap();
            close();
        } catch (err) {
            console.log(err);
        }
    };

    return (
        <Modal close={close} {...props}>
            <form onSubmit={handleSubmit(submit)}>
                <Modal.Title>{t('add_limit')}</Modal.Title>

                <Modal.Content>
                    <SelectField
                        {...register('region_name')}
                        className={css.field}
                        disabled={isSetting || isLoadingRegions || isLoadingUserInfo || !regions}
                        label={t('region')}
                        placeholder={t('choose_region')}
                        options={regionsToSelectFieldOptions(regions)}
                        error={errors.region_name}
                    />

                    <SelectField
                        {...register('instance_type')}
                        className={css.field}
                        disabled={isSetting || isLoadingInstanceTypes || !formRegionName}
                        label={t('instance_type')}
                        placeholder={t('select_type')}
                        error={errors.instance_type}
                        options={[
                            {
                                value: '',
                                title: '',
                            },

                            // ...instanceTypesToSelectFieldOptions(instanceTypes).sort((a, b) => a.title.localeCompare(b.title)),
                            ...instanceTypesToSelectFieldOptions(instanceTypes),
                        ]}
                    />

                    <SelectField
                        {...register('purchase_type')}
                        className={css.field}
                        disabled={isSetting || !formRegionName}
                        label={t('purchase_type')}
                        placeholder={t('select_type')}
                        error={errors.purchase_type}
                        options={[
                            {
                                value: '',
                                title: '',
                            },
                            ...(supportedPurchaseTypes.has('spot')
                                ? [
                                      {
                                          value: 'spot',
                                          title: t('spot'),
                                      },
                                  ]
                                : []),
                            ...(supportedPurchaseTypes.has('on-demand')
                                ? [
                                      {
                                          value: 'on-demand',
                                          title: t('on-demand'),
                                      },
                                  ]
                                : []),
                        ]}
                    />

                    <InputField
                        {...register('maximum')}
                        className={css.field}
                        disabled={isSetting}
                        label={t('maximum')}
                        error={errors.maximum}
                    />
                </Modal.Content>

                <Modal.Buttons>
                    <Button appearance="blue-fill" type="submit" disabled={isSetting}>
                        {t('add')}
                    </Button>

                    <Button appearance="gray-stroke" onClick={close} disabled={isSetting}>
                        {t('cancel')}
                    </Button>
                </Modal.Buttons>
            </form>
        </Modal>
    );
};

export default Limit;
