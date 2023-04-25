import { HelpPanelProps } from 'components';

export type THelpPanelContent = Pick<HelpPanelProps, 'header' | 'footer'> & { body?: HelpPanelProps['children'] };

export interface IAppState {
    userData: IUserSmall | null;
    authData: IUserAuthData | null;
    breadcrumbs: TBreadcrumb[] | null;

    helpPanel: {
        open: boolean;
        content: THelpPanelContent;
    };
}
