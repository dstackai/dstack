import React, { useMemo } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, StatusIndicator, TabsProps, ToggleProps } from 'components';
import { Container, FormInput, FormSelect, FormToggle, Popover, SpaceBetween, Tabs } from 'components';

import { copyToClipboard, generateSecurePassword } from 'libs';

import { FORM_FIELD_NAMES, IDE_OPTIONS } from '../../constants';

import { IRunEnvironmentFormValues } from '../../types';

export type ParamsWizardStepProps = {
    formMethods: UseFormReturn<IRunEnvironmentFormValues>;
    loading?: boolean;
    template?: ITemplate;
};

enum DockerPythonTabs {
    DOCKER = 'docker',
    PYTHON = 'python',
}

export const ParamsWizardStep: React.FC<ParamsWizardStepProps> = ({ formMethods, template, loading }) => {
    const { t } = useTranslation();
    const { control, setValue, watch, getValues } = formMethods;

    const [dockerPythonTab, setDockerPythonTab] = React.useState<DockerPythonTabs>(() => {
        if (getValues(FORM_FIELD_NAMES.image)) {
            return DockerPythonTabs.DOCKER;
        }
        return DockerPythonTabs.PYTHON;
    });

    const isEnabledRepo = Boolean(watch(FORM_FIELD_NAMES.repo_enabled));

    const toggleRepo: ToggleProps['onChange'] = ({ detail }) => {
        if (!detail.checked) {
            setValue(FORM_FIELD_NAMES.repo_url, '');
            setValue(FORM_FIELD_NAMES.repo_path, '');
        }
    };

    const onChangeTab: TabsProps['onChange'] = ({ detail }) => {
        setDockerPythonTab(detail.activeTabId as DockerPythonTabs);

        if (detail.activeTabId === DockerPythonTabs.DOCKER) {
            setValue(FORM_FIELD_NAMES.python, '');
        }

        if (detail.activeTabId === DockerPythonTabs.PYTHON) {
            setValue(FORM_FIELD_NAMES.image, '');
        }

        setValue(FORM_FIELD_NAMES.docker, detail.activeTabId === DockerPythonTabs.DOCKER);
    };

    const defaultPassword = generateSecurePassword(20);

    const paramsMap = useMemo<Map<TTemplateParamType, TTemplateParam>>(() => {
        if (!template) {
            return new Map();
        }

        return new Map(template.parameters.map((parameter) => [parameter.type, parameter]));
    }, [template]);

    const renderName = () => {
        if (!paramsMap.get('name')) {
            return null;
        }

        return (
            <FormInput
                label={t('runs.dev_env.wizard.name')}
                description={t('runs.dev_env.wizard.name_description')}
                constraintText={t('runs.dev_env.wizard.name_constraint')}
                placeholder={t('runs.dev_env.wizard.name_placeholder')}
                control={control}
                name={FORM_FIELD_NAMES.name}
                disabled={loading}
            />
        );
    };

    const copyPassword = () => {
        copyToClipboard(getValues(FORM_FIELD_NAMES.password) ?? '');
    };

    const renderIde = () => {
        if (!paramsMap.get('ide')) {
            return null;
        }

        return (
            <FormSelect
                label={t('runs.dev_env.wizard.ide')}
                description={t('runs.dev_env.wizard.ide_description')}
                control={control}
                name={FORM_FIELD_NAMES.ide}
                options={IDE_OPTIONS}
                disabled={loading}
                defaultValue={'cursor'}
            />
        );
    };

    const renderPythonOrDocker = () => {
        if (!paramsMap.get('python_or_docker')) {
            return null;
        }

        return (
            <Tabs
                onChange={onChangeTab}
                activeTabId={dockerPythonTab}
                tabs={[
                    {
                        label: t('runs.dev_env.wizard.python'),
                        id: DockerPythonTabs.PYTHON,
                        content: (
                            <div>
                                <FormInput
                                    label={t('runs.dev_env.wizard.python')}
                                    description={t('runs.dev_env.wizard.python_description')}
                                    placeholder={t('runs.dev_env.wizard.python_placeholder')}
                                    control={control}
                                    name={FORM_FIELD_NAMES.python}
                                    disabled={loading}
                                />
                            </div>
                        ),
                    },
                    {
                        label: t('runs.dev_env.wizard.docker'),
                        id: DockerPythonTabs.DOCKER,
                        content: (
                            <div>
                                <FormInput
                                    label={t('runs.dev_env.wizard.docker_image')}
                                    description={t('runs.dev_env.wizard.docker_image_description')}
                                    constraintText={t('runs.dev_env.wizard.docker_image_constraint')}
                                    placeholder={t('runs.dev_env.wizard.docker_image_placeholder')}
                                    control={control}
                                    name={FORM_FIELD_NAMES.image}
                                    disabled={loading}
                                />
                            </div>
                        ),
                    },
                ]}
            />
        );
    };

    const renderWorkingDir = () => {
        if (!paramsMap.get('working_dir')) {
            return null;
        }

        return (
            <FormInput
                label={t('runs.dev_env.wizard.working_dir')}
                description={t('runs.dev_env.wizard.working_dir_description')}
                constraintText={t('runs.dev_env.wizard.working_dir_constraint')}
                placeholder={t('runs.dev_env.wizard.working_dir_placeholder')}
                control={control}
                name="working_dir"
                disabled={loading}
            />
        );
    };

    const renderRepo = () => {
        if (!paramsMap.get('repo')) {
            return null;
        }

        return (
            <SpaceBetween direction="vertical" size="l">
                <FormToggle
                    control={control}
                    defaultValue={false}
                    label={t('runs.dev_env.wizard.repo')}
                    name={FORM_FIELD_NAMES.repo_enabled}
                    disabled={loading}
                    onChange={toggleRepo}
                />

                {isEnabledRepo && (
                    <SpaceBetween direction="vertical" size="l">
                        <FormInput
                            label={t('runs.dev_env.wizard.repo_url')}
                            description={t('runs.dev_env.wizard.repo_url_description')}
                            constraintText={t('runs.dev_env.wizard.repo_url_constraint')}
                            placeholder={t('runs.dev_env.wizard.repo_url_placeholder')}
                            control={control}
                            name="repo_url"
                            disabled={loading}
                        />

                        <FormInput
                            label={t('runs.dev_env.wizard.repo_path')}
                            description={t('runs.dev_env.wizard.repo_path_description')}
                            constraintText={t('runs.dev_env.wizard.repo_path_constraint')}
                            placeholder={t('runs.dev_env.wizard.repo_path_placeholder')}
                            control={control}
                            name="repo_path"
                            disabled={loading}
                        />
                    </SpaceBetween>
                )}
            </SpaceBetween>
        );
    };

    const renderEnv = () => {
        const envParameter = paramsMap.get('env');

        if (!envParameter) {
            return null;
        }

        return (
            <FormInput
                label={envParameter.title}
                control={control}
                name={FORM_FIELD_NAMES.password}
                defaultValue={defaultPassword}
                type="text"
                disabled={loading}
                secondaryControl={
                    <Popover
                        dismissButton={false}
                        position="top"
                        size="small"
                        triggerType="custom"
                        content={<StatusIndicator type="success">Password copied</StatusIndicator>}
                    >
                        <Button disabled={loading} formAction="none" iconName="copy" variant="link" onClick={copyPassword} />
                    </Popover>
                }
            />
        );
    };

    return (
        <Container>
            <SpaceBetween direction="vertical" size="l">
                {renderName()}
                {renderIde()}
                {renderEnv()}
                {renderPythonOrDocker()}
                {renderWorkingDir()}
                {renderRepo()}
            </SpaceBetween>
        </Container>
    );
};
