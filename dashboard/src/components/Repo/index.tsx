import React from 'react';
import cn from 'classnames';
import Tooltip from 'components/Tooltip';
import { ReactComponent as GithubCircleIcon } from 'assets/icons/github-circle.svg';
import { ReactComponent as SourceBranchIcon } from 'assets/icons/source-branch.svg';
import { ReactComponent as SourceCommitIcon } from 'assets/icons/source-commit.svg';
import { formatRepoUrl, getRepoName, getRepoTreeUrl } from 'libs';
import css from './index.module.css';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const Repo: React.FC<Props> = ({ className, children, ...props }) => {
    return (
        <div className={cn(css.repo, className)} {...props}>
            {children}
        </div>
    );
};

export interface UrlProps extends React.HTMLAttributes<HTMLDivElement> {
    url: string;
}

const Url: React.FC<UrlProps> = ({ className, url, ...props }) => {
    const normalizedUrl = formatRepoUrl(url);

    if (!normalizedUrl) return null;

    return (
        <div className={cn(css.url, className)} {...props}>
            <GithubCircleIcon width={12} height={12} />

            <a href={normalizedUrl} target="_blank">
                {normalizedUrl}
            </a>
        </div>
    );
};

export interface BranchProps extends React.HTMLAttributes<HTMLDivElement> {
    branch: string;
}

const Branch: React.FC<BranchProps> = ({ className, branch, ...props }) => {
    if (!branch) return null;

    return (
        <div className={cn(css.branch, className, 'mono-font')} {...props}>
            <SourceBranchIcon />
            <span>{branch}</span>
        </div>
    );
};

export interface HashProps {
    className?: string;
    repoUrl: string;
    hash: string;
}

const Hash: React.FC<HashProps> = ({ className, repoUrl, hash }) => {
    const treeUrl = getRepoTreeUrl(repoUrl, hash);

    if (treeUrl)
        return (
            <a className={cn(css.hash, className, 'mono-font')} href={treeUrl} target="_blank">
                <SourceCommitIcon />
                <span>{hash}</span>
            </a>
        );

    return (
        <Tooltip overlayContent={hash}>
            <div className={cn(css.hash, className, 'mono-font')}>
                <SourceCommitIcon />
                <span>{hash}</span>
            </div>
        </Tooltip>
    );
};

export interface NameProps {
    className?: string;
    repoUrl: string;
}

const Name: React.FC<NameProps> = ({ className, repoUrl }) => {
    return (
        <a href={repoUrl} target="_blank" className={cn(css.name, className, 'mono-font')}>
            {getRepoName(repoUrl)}
        </a>
    );
};

export default Object.assign(Repo, {
    Url,
    Branch,
    Hash,
    Name,
});
