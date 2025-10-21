import { useAppSelector } from 'hooks';
import { copyToClipboard } from 'libs';

import { selectAuthToken } from 'App/slice';

type Args = {
    projectName: string;
};
export const useConfigProjectCliCommand = ({ projectName }: Args) => {
    const currentUserToken = useAppSelector(selectAuthToken);

    const cliCommand = `dstack project add \\\n  --url ${location.origin} \\\n  --name ${projectName} \\\n  --token ${currentUserToken}`;

    const copyCliCommand = () => {
        copyToClipboard(cliCommand);
    };

    return [cliCommand, copyCliCommand] as const;
};
