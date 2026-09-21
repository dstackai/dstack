import { product } from 'product';

import { router } from './router';

const MEASUREMENT_ID = process.env.GA_MEASUREMENT_ID;

export const initAnalytics = () => {
    if (!product.isSky || !MEASUREMENT_ID) return;

    window.dataLayer = window.dataLayer || [];
    window.gtag = function () {
        // eslint-disable-next-line prefer-rest-params -- gtag expects an arguments object.
        window.dataLayer?.push(arguments);
    };
    window.gtag('js', new Date());
    window.gtag('set', {
        page_location: window.location.origin,
        page_referrer: '',
        page_title: 'dstack Sky',
    });
    // Enhanced Measurement must be disabled for the Sky stream.
    window.gtag('config', MEASUREMENT_ID, { send_page_view: false });

    let lastLocationKey: string | undefined;
    let previousPageLocation = '';
    const trackPageView = () => {
        const { location, matches, errors } = router.state;
        if (location.key === lastLocationKey) return;

        // Route templates exclude names, IDs, and OAuth query parameters.
        const path = errors ? '/404' : matches.reduce((path, { route }) => route.path || path, '/404');
        const pageLocation = window.location.origin + path;
        window.gtag?.('set', { page_location: pageLocation, page_referrer: previousPageLocation });
        window.gtag?.('event', 'page_view');
        previousPageLocation = pageLocation;
        lastLocationKey = location.key;
    };

    router.subscribe(trackPageView);
    trackPageView();

    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
    document.head.appendChild(script);
};
