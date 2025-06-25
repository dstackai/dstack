import { TutorialPanelProps } from '@cloudscape-design/components';
import { Mode } from '@cloudscape-design/global-styles';

import { HelpPanelProps } from 'components';

export type THelpPanelContent = Pick<HelpPanelProps, 'header' | 'footer'> & { body?: HelpPanelProps['children'] };

export enum ToolsTabs {
    INFO = 'info',
    TUTORIAL = 'tutorial',
}

export interface ITutorialItem extends TutorialPanelProps.Tutorial {
    id: number;
    startCallback?: (tutorial: ITutorialItem) => void;
    startWithoutActivation?: boolean;
    finishCallback?: (tutorial: ITutorialItem) => void;
}

export interface IAppState {
    userData: IUser | null;
    authData: IUserAuthData | null;
    breadcrumbs: TBreadcrumb[] | null;
    systemMode: Mode;
    toolsPanelState: {
        isOpen: boolean;
        tab: ToolsTabs;
    };

    helpPanel: {
        content: THelpPanelContent;
    };

    tutorialPanel: {
        billingCompleted: boolean;
        configureCLICompleted: boolean;
        discordCompleted: boolean;
        tallyCompleted: boolean;
        quickStartCompleted: boolean;
        hideStartUp: boolean | null;
    };
}
