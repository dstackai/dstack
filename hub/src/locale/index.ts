import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './en.json';

i18n.use(initReactI18next).init({
    returnNull: false,
    resources: {
        en: {
            translation: en,
        },
    },
    fallbackLng: 'en',

    interpolation: {
        escapeValue: false,
    },
});
