import React from 'react';
import cn from 'classnames';
import css from './index.module.css';
import Button from '../../../../../components/Button';
import { ReactComponent as CopyIcon } from '../../../../../assets/icons/content-copy.svg';
import { copyToClipboard } from '../../../../../libs';
import { cloneCode, installCliCode, runWorkflow } from './data';
import CodeViewer from '../../../../../components/CodeViewer';

export type Props = React.HTMLAttributes<HTMLDivElement>;

const EmptyRepositoryList: React.FC<Props> = ({ className, ...props }) => {
    return (
        <div className={cn(css.empty, className)} {...props}>
            <div className={css.title}>👋 Hey-hey!</div>
            <div className={css.text}>To start working with dstack just follow these steps:</div>

            <div className={css.step}>
                <div className={css.stepTitle}>1. Install CLI:</div>

                <div className={css.codeWrapper}>
                    <CodeViewer className={css.codeViewer} language="python">
                        {installCliCode}
                    </CodeViewer>

                    <Button
                        className={css.copy}
                        displayAsRound
                        dimension="s"
                        appearance="gray-transparent"
                        icon={<CopyIcon />}
                        onClick={() => copyToClipboard(installCliCode)}
                    />
                </div>
            </div>

            <div className={css.step}>
                <div className={css.stepTitle}>2. Clone GitHub project:</div>

                <div className={css.codeWrapper}>
                    <CodeViewer className={css.codeViewer} language="python">
                        {cloneCode}
                    </CodeViewer>

                    <Button
                        className={css.copy}
                        displayAsRound
                        dimension="s"
                        appearance="gray-transparent"
                        icon={<CopyIcon />}
                        onClick={() => copyToClipboard(cloneCode)}
                    />
                </div>
            </div>

            <div className={css.step}>
                <div className={css.stepTitle}>3. Run workflow</div>

                <div className={css.codeWrapper}>
                    <CodeViewer className={css.codeViewer} language="python">
                        {runWorkflow}
                    </CodeViewer>

                    <Button
                        className={css.copy}
                        displayAsRound
                        dimension="s"
                        appearance="gray-transparent"
                        icon={<CopyIcon />}
                        onClick={() => copyToClipboard(runWorkflow)}
                    />
                </div>
            </div>

            <div className={css.text}>
                Have any questions? Learn more in the{' '}
                <a href="/" target="_blank">
                    Documentation
                </a>
                .
            </div>
        </div>
    );
};

export default EmptyRepositoryList;
