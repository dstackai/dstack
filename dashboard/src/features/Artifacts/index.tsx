import React, { useMemo, useState } from 'react';
import cn from 'classnames';
import { useTranslation } from 'react-i18next';
import { getFolderNameFromPath } from 'libs';
import EmptyMessage from './EmptyMessage';
import { useGetArtifactObjectsQuery } from 'services/artifacts';
import { ReactComponent as ChevronUpIcon } from 'assets/icons/chevron-up.svg';
import { ReactComponent as ChevronDownIcon } from 'assets/icons/chevron-down.svg';
import { ReactComponent as FolderOutlineIcon } from 'assets/icons/folder-outline.svg';
import { ReactComponent as FileDownloadOutlineIcon } from 'assets/icons/file-download-outline.svg';
import css from './index.module.css';

export interface FileProps {
    name: string;
    nestingLevel: number;
    noBorder?: boolean;
}

const File: React.FC<FileProps> = ({ name, nestingLevel, noBorder }) => {
    return (
        <div className={cn(css.file, { 'no-border': noBorder })} style={{ paddingLeft: `${(nestingLevel - 1) * 18 + 32}px` }}>
            <a href="#" title={name}>
                <FileDownloadOutlineIcon />
                {name}
            </a>
        </div>
    );
};

type TArtifactFolderProps = IArtifactsFetchParams & {
    open?: boolean;
    nestingLevel?: number;
    noBorder?: boolean;
};

const Folder: React.FC<TArtifactFolderProps> = ({
    path,
    noBorder = true,
    nestingLevel = 0,
    open: defaultOpen = false,
    ...params
}) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState<boolean>(defaultOpen);

    const folderName = useMemo<string>(() => getFolderNameFromPath(path), [path]);

    const { data, isLoading } = useGetArtifactObjectsQuery(
        { path, ...params },
        {
            skip: !open,
        },
    );

    return (
        <div className={css.folder}>
            <div
                className={cn(css.folderName, { 'no-border': noBorder && !open })}
                style={{ paddingLeft: `${nestingLevel * 18}px` }}
                onClick={() => setOpen((val) => !val)}
                title={path}
            >
                {open ? <ChevronDownIcon /> : <ChevronUpIcon className={css.closedIcon} />}
                <FolderOutlineIcon />
                {folderName}
            </div>

            {open && (
                <div className={css.includes}>
                    {isLoading && <div className={css.loading} style={{ marginLeft: `${(nestingLevel + 1) * 18}px` }} />}

                    {data &&
                        data.map((i, index) =>
                            i.folder ? (
                                <Folder
                                    nestingLevel={nestingLevel + 1}
                                    key={index}
                                    path={[path, i.name].join('/')}
                                    noBorder={noBorder && index === data.length - 1}
                                    {...params}
                                />
                            ) : (
                                <File
                                    noBorder={noBorder && index === data.length - 1}
                                    nestingLevel={nestingLevel + 1}
                                    key={index}
                                    name={i.name}
                                />
                            ),
                        )}

                    {!isLoading && !data?.length && <EmptyMessage>{t('no_files_here')}</EmptyMessage>}
                </div>
            )}
        </div>
    );
};

export interface Props extends Omit<IArtifactsFetchParams, 'path' | 'job_id'> {
    artifacts?: TArtifacts;
    className?: string;
}

const Artifacts: React.FC<Props> = ({ artifacts, className, ...params }) => {
    if (!artifacts) return null;

    return (
        <div className={cn(css.artifacts, className)}>
            {artifacts.map((f, index) => (
                <Folder path={f.artifact_path} key={index} job_id={f.job_id} open {...params} />
            ))}
        </div>
    );
};

export default Artifacts;
