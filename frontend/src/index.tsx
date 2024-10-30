import React from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { RouterProvider } from 'react-router-dom';
import { applyTheme, Theme } from '@cloudscape-design/components/theming';

import { router } from './router';
import { store } from './store';

import '@cloudscape-design/global-styles/index.css';
import 'ace-builds/css/ace.css';
import 'ace-builds/css/theme/cloud_editor.css';
import 'ace-builds/css/theme/cloud_editor_dark.css';
import 'assets/css/index.css';
import '@xterm/xterm/css/xterm.css';

import 'locale';

const container = document.getElementById('root');

const theme: Theme = {
    tokens: {
        fontFamilyBase: "'Roboto', 'Open Sans', 'Helvetica Neue', Arial, sans-serif",
    },
};

applyTheme({ theme });

if (container) {
    const root = createRoot(container);

    root.render(
        <React.StrictMode>
            <Provider store={store}>
                <RouterProvider router={router} />
            </Provider>
        </React.StrictMode>,
    );
}
