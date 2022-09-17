import React, {FC, useState} from 'react';
import WindowFrame from 'components/WindowFrame';
import css from './index.module.css';
import LandingTabs from 'components/LandingTabs';
import CodeViewer from 'components/CodeViewer';

import cn from 'classnames';

const DefineWorkflowsSnippet: FC = () => {
    const [tab, setTab] = useState<'workflows' | 'variables'>('workflows');

    return (
        <WindowFrame className={cn(css.window, css.codeView)}>
            <LandingTabs
                className={css.tabs}
                onChange={(tab) => setTab(tab as 'workflows')}
                value={tab}
                tabs={[
                    {
                        label: '.dstack/workflows.yaml',
                        value: 'workflows',
                    },
                ]}
            />

            <div>
                <CodeViewer className={css.code} language="yaml">
                    {`workflows:
    - name: download
      provider: bash
      python: 3.10
      commands:
        - pip install -r requirements.txt
        - python mnist/download.py
      artifacts:
        - path: data
    
    - name: train
      deps:
        - tag: mnist_data
      provider: bash
      python: 3.10
      commands:
        - pip install -r requirements.txt
        - python mnist/train.py
      artifacts:
        - path: lightning_logs
      resources:
          interruptible: true
          gpu: 1`}
                </CodeViewer>
            </div>
        </WindowFrame>
    );
};

const RunCommandsSnippet: FC = () => {
    const [tab, setTab] = useState<'terminal'>('terminal');

    return (
        <WindowFrame className={cn(css.window, css.codeView)}>
            <LandingTabs
                className={css.tabs}
                onChange={(tab) => setTab(tab as 'terminal')}
                value={tab}
                tabs={[
                    {
                        label: 'Terminal',
                        value: 'terminal',
                    },
                ]}
            />

            <div>
                <CodeViewer className={css.code} language="bash">
                    {`$ dstack run train

  ┌───────────────┬──────────────┬─────────────────┬─────┬──────────────┬───────────┐
  │ Run           │ Provider     │ Status          │ App │ Artifacts    │ Submitted │
  ├───────────────┼──────────────┼─────────────────┼─────┼──────────────┼───────────┤
  │ witty-husky-1 │ python       │ Provisioning... │     │ model        │ now       │
  └───────────────┴──────────────┴─────────────────┴─────┴──────────────┴───────────┘

  Provisioning... It may take up to a minute. ✓

  To interrupt, press Ctrl+C.

  Successfully installed certifi-2022.6.15 charset-normalizer-2.1.0 idna-3.3 numpy-1.23.1 
  pillow-9.2.0 requests-2.28.1 torch-1.12.0 torchvision-0.13.0 typing-extensions-4.3.0
  urllib3-1.26.11
  Downloading http://yann.lecun.com/exdb/mnist/train-labels-idx1-ubyte.gz to 
    data/MNIST/raw/train-labels-idx1-ubyte.gz 100.0%
  Extracting data/MNIST/raw/train-labels-idx1-ubyte.gz to data/MNIST/raw
  
  Train Epoch: 1 [0/60000 (0%)]       Loss: 2.329474
  Train Epoch: 1 [640/60000 (1%)]     Loss: 1.425063
  Train Epoch: 1 [1280/60000 (2%)]    Loss: 0.815459
  Train Epoch: 1 [1920/60000 (3%)]    Loss: 0.626226`}
                </CodeViewer>
            </div>
        </WindowFrame>
    );
};

const InstallCLISnippet: FC = () => {
    return (
        <WindowFrame className={cn(css.window, css.codeView)}>
            <div>
                <CodeViewer className={css.code} language="bash">
                    {`
  $ pip install dstack
  Collecting dstack
  Downloading dstack-0.0.5-py3-none-any.whl (67 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 67.9/67.9 KB 8.9 MB/s eta 0:00:00
  Installing collected packages: dstack
  
  $ dstack config
  Token: fe15b9ac-68e8-4cc0-8281-e0ba0bda7c3d
    
  $ █`}
                </CodeViewer>
            </div>
        </WindowFrame>
    );
};

export const opportunities = [
    {
        title: 'Define workflows',
        align: 'left',
        asset: <DefineWorkflowsSnippet />,
        points: [
            {
                text:
                    'Workflows are defined declaratively within the project.\n' +
                    'Every workflow may specify the provider, dependencies, commands, artifacts, ' +
                    'hardware requirements, environment variables, and more.\n' +
                    'The provider defines how the workflow is executed and what properties can be specified for the workflow.\n' +
                    'dstack offers multiple providers that allow running tasks, applications, and dev environments.',
            },
        ],
    },
    {
        title: 'Run workflows',
        align: 'right',
        asset: <RunCommandsSnippet />,
        points: [
            {
                text:
                    'When you run a workflow withing a Git repository, dstack detects the current branch, commit hash, ' +
                    'and local changes, and uses it on the cloud instance(s) to run the workflow.\n' +
                    'dstack automatically sets up environment for the workflow. It pre-installs the right CUDA driver ' +
                    'and Conda.\n' +
                    'You can see the output logs in real-time as the workflow is running.',
            },
        ],
    },
    /*{
        title: 'Store artifacts in cloud',
        align: 'right',
        asset: (
            <WindowFrame className={css.window}>
                <div className={css.image}>
                    <img src={slide3} srcSet={`${slide3HighRes} 2x`} alt={`slide-3`} />
                </div>
            </WindowFrame>
        ),
        points: [
            {
                text: 'XXX',
            },
        ],
    }, */
    /*{
        title: 'Add your cloud credentials',
        align: 'right',
        asset: (
            <WindowFrame className={css.window}>
                <div className={css.image}>
                    <img src={slide2} srcSet={`${slide2HighRes} 2x`} alt={`slide-2`} />
                </div>
            </WindowFrame>
        ),
        points: [
            {
                text:
                    'Finally, to let dstack provision infrastructure in your cloud account as ' +
                    'you run commands, you have to go to the Settings of your dstack account, and the ' +
                    'credentials of your cloud account.\n' +
                    'Also, you can configure your own cloud storage to store artifacts.',
            },
        ],
    },*/
];
