import React from 'react';
import ReactDOM from 'react-dom';
import { Provider } from 'react-redux';
import { BrowserRouter as Router } from 'react-router-dom';
import App from 'App';
import { store } from './store';
import 'assets/css/index.css';
import 'rc-tooltip/assets/bootstrap.css';
import 'assets/css/diff2html.css';
import 'locale';

ReactDOM.render(
    <React.StrictMode>
        <Provider store={store}>
            <Router>
                <App />
            </Router>
        </Provider>
    </React.StrictMode>,
    document.getElementById('root'),
);
