import React, { useEffect } from 'react';

export const TallyComponent: React.FC = () => {
    useEffect(() => {
        const widgetScriptSrc = 'https://tally.so/widgets/embed.js';

        if (document.querySelector(`script[src="${widgetScriptSrc}"]`) === null) {
            const script = document.createElement('script');
            script.src = widgetScriptSrc;
            document.body.appendChild(script);
            return;
        }
    }, []);

    return null;
};
