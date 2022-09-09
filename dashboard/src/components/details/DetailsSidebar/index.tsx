import React from 'react';
import cn from 'classnames';
import Repo from 'components/Repo';
import Tooltip from 'components/Tooltip';
import css from './index.module.css';

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    children?: React.ReactNode;
}

const DetailsSidebar: React.FC<Props> = ({ children, className, ...props }) => {
    return (
        <aside className={cn(css.sidebar, className)} {...props}>
            {children}
        </aside>
    );
};

interface SectionProps extends React.HTMLAttributes<HTMLDivElement> {
    title?: string;
    children?: React.ReactNode;
}

const Section: React.FC<SectionProps> = ({ title, children, className, ...props }) => {
    return (
        <section className={cn(css.section, className)} {...props}>
            {title && <h4 className={css.sectionTitle}>{title}</h4>}
            {children}
        </section>
    );
};

interface PropertyProps extends React.HTMLAttributes<HTMLDivElement> {
    name: string;
    children?: React.ReactNode;
    align?: 'start' | 'center' | 'end';
    tooltip?: string;
}

const Property: React.FC<PropertyProps> = ({ name, tooltip, children, align, className, ...props }) => {
    return (
        <div className={cn(css.prop, className, { [css[`align-${align}`]]: Boolean(align) })} {...props}>
            {tooltip ? (
                <Tooltip placement="topLeft" overlayContent={tooltip}>
                    <div className={css.propName}>{name}</div>
                </Tooltip>
            ) : (
                <div className={css.propName}>{name}</div>
            )}

            <div className={css.propValue}>{children}</div>
        </div>
    );
};

interface RepoAttrsProps extends React.HTMLAttributes<HTMLDivElement> {
    repoUrl: string;
    hash: string;
    branch: string;
}

const RepoAttrs: React.FC<RepoAttrsProps> = ({ hash, repoUrl, branch, children, className, ...props }) => {
    return (
        <React.Fragment>
            <Repo.Name repoUrl={repoUrl} />

            <div className={cn(css.repoAttrs, className)} {...props}>
                <Repo.Hash className={css.hash} repoUrl={repoUrl} hash={hash} />
                <Repo.Branch className={css.branch} branch={branch} />
            </div>

            {children}
        </React.Fragment>
    );
};

export default Object.assign(DetailsSidebar, {
    Section,
    Property,
    RepoAttrs,
});
