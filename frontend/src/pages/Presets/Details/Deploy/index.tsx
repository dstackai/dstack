import React, { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import {
    Box,
    Button,
    Container,
    ExpandableSection,
    Header,
    Link,
    Loader,
    Popover,
    SpaceBetween,
    StatusIndicator,
    Tabs,
    Wizard,
} from 'components';

import { FLEETS_DOCS_URL } from 'consts';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useGetPresetQuery } from 'services/preset';

const UV_INSTALL_COMMAND = 'uv tool install dstack -U';
const PIP_INSTALL_COMMAND = 'pip install dstack -U';

const CopyableCommand: FC<{ command: string }> = ({ command }) => {
    const { t } = useTranslation();

    return (
        <SpaceBetween size="xs" direction="horizontal" alignItems="center">
            <Box variant="code">{command}</Box>
            <Popover
                dismissButton={false}
                position="top"
                size="small"
                triggerType="custom"
                content={<StatusIndicator type="success">{t('common.copied')}</StatusIndicator>}
            >
                <Button formAction="none" iconName="copy" variant="normal" onClick={() => copyToClipboard(command)} />
            </Popover>
        </SpaceBetween>
    );
};

export const PresetDeploy: FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const navigate = useNavigate();
    const paramProjectName = params.projectName ?? '';
    const paramPresetId = params.presetId ?? '';
    const [activeStepIndex, setActiveStepIndex] = React.useState(0);

    const { data: preset, isLoading } = useGetPresetQuery({
        project_name: paramProjectName,
        id: paramPresetId,
    });

    if (isLoading || !preset)
        return (
            <Container>
                <Loader />
            </Container>
        );

    // A preset is pulled by whatever reference reaches it: its name while one
    // points at it, its id otherwise.
    const reference = `${preset.project_name}/${preset.name ?? preset.id}`;
    // Once pulled, it is referred to locally: a named preset keeps the
    // qualified name, while one pulled by id lands untagged and is its id.
    const localReference = preset.name ? reference : preset.id;
    // A scratch file the next step applies, so the name stays the same for
    // every preset rather than tracking the preset's own.
    const configurationFile = 'preset.dstack.yml';

    return (
        <Container header={<Header variant="h2">{t('presets.deploy')}</Header>}>
            <Wizard
                i18nStrings={{
                    stepNumberLabel: (stepNumber) => `Step ${stepNumber}`,
                    collapsedStepsLabel: (stepNumber, stepsCount) => `Step ${stepNumber} of ${stepsCount}`,
                    navigationAriaLabel: 'Steps',
                    cancelButton: t('common.cancel'),
                    previousButton: 'Previous',
                    nextButton: 'Next',
                }}
                onNavigate={({ detail }) => setActiveStepIndex(detail.requestedStepIndex)}
                activeStepIndex={activeStepIndex}
                onCancel={() => navigate(ROUTES.PRESETS.DETAILS.FORMAT(paramProjectName, paramPresetId))}
                onSubmit={() => navigate(ROUTES.PRESETS.DETAILS.FORMAT(paramProjectName, paramPresetId))}
                submitButtonText="Done"
                steps={[
                    {
                        title: t('presets.step_pull'),
                        description: t('presets.step_pull_description'),
                        content: (
                            <SpaceBetween size="s">
                                <CopyableCommand command={`dstack preset pull ${reference}`} />

                                <ExpandableSection headerText={t('presets.no_cli')}>
                                    <SpaceBetween size="s">
                                        <Box />
                                        <Box>{t('presets.no_cli_description')}</Box>

                                        <Tabs
                                            variant="container"
                                            tabs={[
                                                {
                                                    label: 'uv',
                                                    id: 'uv',
                                                    content: <CopyableCommand command={UV_INSTALL_COMMAND} />,
                                                },
                                                {
                                                    label: 'pip',
                                                    id: 'pip',
                                                    content: <CopyableCommand command={PIP_INSTALL_COMMAND} />,
                                                },
                                            ]}
                                        />
                                    </SpaceBetween>
                                </ExpandableSection>
                            </SpaceBetween>
                        ),
                    },
                    {
                        title: t('presets.step_export'),
                        description: t('presets.step_export_description'),
                        content: <CopyableCommand command={`dstack preset export ${localReference} -f ${configurationFile}`} />,
                    },
                    {
                        title: t('presets.step_apply'),
                        description: t('presets.step_apply_description'),
                        content: (
                            <SpaceBetween size="s">
                                <CopyableCommand command={`dstack apply -f ${configurationFile}`} />

                                <ExpandableSection headerText={t('presets.no_fleet')}>
                                    <SpaceBetween size="s">
                                        <Box />
                                        <Box>
                                            {t('presets.no_fleet_description')}{' '}
                                            <Link href={FLEETS_DOCS_URL} external>
                                                {t('presets.fleets_link')}
                                            </Link>
                                        </Box>
                                    </SpaceBetween>
                                </ExpandableSection>
                            </SpaceBetween>
                        ),
                    },
                ]}
            />
        </Container>
    );
};
