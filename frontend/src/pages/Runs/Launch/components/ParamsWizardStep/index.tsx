import React, { useMemo } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button, InfoLink, StatusIndicator, TabsProps, ToggleProps } from 'components';
import { Container, FormInput, FormSelect, FormToggle, Popover, SpaceBetween, Tabs } from 'components';

import { useHelpPanel } from 'hooks';
import { copyToClipboard, generateSecurePassword } from 'libs';

import { FORM_FIELD_NAMES, IDE_OPTIONS, PASSWORD_INFO } from '../../constants';

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
    const [openHelpPanel] = useHelpPanel();

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
                label={t('runs.launch.wizard.name')}
                description={t('runs.launch.wizard.name_description')}
                constraintText={t('runs.launch.wizard.name_constraint')}
                placeholder={t('runs.launch.wizard.name_placeholder')}
                control={control}
                name={FORM_FIELD_NAMES.name}
                disabled={loading}
            />
        );
    };

    const copyPassword = () => {
        copyToClipboard(getValues(FORM_FIELD_NAMES.password) ?? '');
        setValue(FORM_FIELD_NAMES.password_copied, true, { shouldValidate: true });
    };

    const renderIde = () => {
        if (!paramsMap.get('ide')) {
            return null;
        }

        return (
            <FormSelect
                label={t('runs.launch.wizard.ide')}
                description={t('runs.launch.wizard.ide_description')}
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
                        label: t('runs.launch.wizard.python'),
                        id: DockerPythonTabs.PYTHON,
                        content: (
                            <div>
                                <FormInput
                                    label={t('runs.launch.wizard.python')}
                                    description={t('runs.launch.wizard.python_description')}
                                    placeholder={t('runs.launch.wizard.python_placeholder')}
                                    control={control}
                                    name={FORM_FIELD_NAMES.python}
                                    disabled={loading}
                                />
                            </div>
                        ),
                    },
                    {
                        label: t('runs.launch.wizard.docker'),
                        id: DockerPythonTabs.DOCKER,
                        content: (
                            <div>
                                <FormInput
                                    label={t('runs.launch.wizard.docker_image')}
                                    description={t('runs.launch.wizard.docker_image_description')}
                                    constraintText={t('runs.launch.wizard.docker_image_constraint')}
                                    placeholder={t('runs.launch.wizard.docker_image_placeholder')}
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
                label={t('runs.launch.wizard.working_dir')}
                description={t('runs.launch.wizard.working_dir_description')}
                constraintText={t('runs.launch.wizard.working_dir_constraint')}
                placeholder={t('runs.launch.wizard.working_dir_placeholder')}
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
                    label={t('runs.launch.wizard.repo')}
                    name={FORM_FIELD_NAMES.repo_enabled}
                    disabled={loading}
                    onChange={toggleRepo}
                />

                {isEnabledRepo && (
                    <SpaceBetween direction="vertical" size="l">
                        <FormInput
                            label={t('runs.launch.wizard.repo_url')}
                            description={t('runs.launch.wizard.repo_url_description')}
                            constraintText={t('runs.launch.wizard.repo_url_constraint')}
                            placeholder={t('runs.launch.wizard.repo_url_placeholder')}
                            control={control}
                            name="repo_url"
                            disabled={loading}
                        />

                        <FormInput
                            label={t('runs.launch.wizard.repo_path')}
                            description={t('runs.launch.wizard.repo_path_description')}
                            constraintText={t('runs.launch.wizard.repo_path_constraint')}
                            placeholder={t('runs.launch.wizard.repo_path_placeholder')}
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

        const isRandomPassword = envParameter.value === '$random-password';

        if (isRandomPassword) {
            return (
                <FormInput
                    label={envParameter.title}
                    info={<InfoLink onFollow={() => openHelpPanel(PASSWORD_INFO)} />}
                    control={control}
                    name={FORM_FIELD_NAMES.password}
                    defaultValue={defaultPassword}
                    type="password"
                    disabled={loading}
                    secondaryControl={
                        <Popover
                            dismissButton={false}
                            position="top"
                            size="small"
                            triggerType="custom"
                            content={<StatusIndicator type="success">Password copied</StatusIndicator>}
                        >
                            <Button
                                disabled={loading}
                                formAction="none"
                                iconName="copy"
                                variant="link"
                                onClick={copyPassword}
                            />
                        </Popover>
                    }
                />
            );
        }

        return (
            <FormInput
                label={envParameter.title}
                control={control}
                name={FORM_FIELD_NAMES.password}
                defaultValue={envParameter.value ?? ''}
                type="text"
                disabled={loading}
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
