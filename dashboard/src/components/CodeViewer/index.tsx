import React, { useEffect } from 'react';
import cn from 'classnames';
import Prism from 'prismjs';
import 'prismjs/components/prism-yaml';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-python';
import 'prismjs/themes/prism.css';
import css from './index.module.css';

export interface Props {
    className?: string;
    language: string;
    children: string;
}

const CodeViewer: React.FC<Props> = ({ className, language, children }) => {
    useEffect(() => {
        Prism.languages['bash'] = {
            'command': {
                pattern: /\$[^\\\n]+/,
            },
            'command-2': {
                pattern: /\\\n    [^\n]+/,
            },
            'progress': {
                pattern: /━+/,
            },
            'progress-measure-1': {
                pattern: /[\d.]+\/[\d.]+/,
            },
            'progress-measure-2': {
                pattern: /[\d.]+ MB\/s+/,
            },
            'progress-measure-3': {
                pattern: /\d+:\d+:\d+/,
            },
            'table-reserved': {
                pattern: /Provisioning... It may take up to a minute./,
            },
            'table-gray': {
                pattern: /To interrupt, press Ctrl\+C\./,
            },
            'table-green': {
                pattern: /✓/,
            },
            'url': {
                pattern: /http:\/\/\S*[^(.+)\s\n\r]/,
            },
            'table-run-name': {
                pattern: / witty-husky-1\s+/,
            },
            'table-provisioning': {
                pattern: / +Provisioning\.\.\.\s+/,
            },
            'table-fields': {
                pattern: / (python|model|now)\s+/,
            },
            'table': {
                pattern: /│ (.+)\s+/,
            },
        };
        Prism.highlightAll();
    }, []);

    return (
        <div className={cn(css.code, className)}>
            <pre>
                <code className={`language-${language}`}>{children}</code>
            </pre>
        </div>
    );
};

export default CodeViewer;
