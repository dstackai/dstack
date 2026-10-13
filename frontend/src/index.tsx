import React from 'react';
import { Provider as BusProvider } from 'react-bus';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { RouterProvider } from 'react-router-dom';
import { I18nProvider } from '@cloudscape-design/components/i18n';
import enMessages from '@cloudscape-design/components/i18n/messages/all.en.json';
import { applyTheme, Theme } from '@cloudscape-design/components/theming';

import { initAnalytics } from './analytics';
import { router } from './router';
import { store } from './store';

import '@cloudscape-design/global-styles/index.css';
import 'ace-builds/css/ace.css';
import 'ace-builds/css/theme/cloud_editor.css';
import 'ace-builds/css/theme/cloud_editor_dark.css';
import 'assets/css/index.css';

import 'locale';

initAnalytics();

const container = document.getElementById('root');

const theme: Theme = {
    tokens: {
        fontFamilyBase:
            'metro-web, Metro, -apple-system, "system-ui", "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif',
        fontSizeHeadingS: '15px',
        fontSizeHeadingL: '19px',
        fontSizeHeadingXl: '22px',
        fontSizeDisplayL: '40px',
    },
};

applyTheme({ theme });

if (container) {
    const root = createRoot(container);

    root.render(
        <React.StrictMode>
            {/* Cloudscape's default labels, e.g. the property filter's Apply and Cancel, for any a page leaves out. */}
            <I18nProvider locale="en" messages={[enMessages]}>
                <Provider store={store}>
                    <BusProvider>
                        <RouterProvider router={router} />
                    </BusProvider>
                </Provider>
            </I18nProvider>
        </React.StrictMode>,
    );
}
