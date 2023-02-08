import React from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { BrowserRouter as Router } from 'react-router-dom';
import App from 'App';
import { store } from './store';
import '@cloudscape-design/global-styles/index.css';
import 'assets/css/index.css';
import 'locale';

const container = document.getElementById('root');

if (container) {
    const root = createRoot(container);

    root.render(
        <React.StrictMode>
            <Provider store={store}>
                <Router>
                    <App />
                </Router>
            </Provider>
        </React.StrictMode>,
    );
}
