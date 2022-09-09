import { format } from 'date-fns';

export const awsLogEventToString = (event: IAWSEvent): string => {
    if (!event.message) return '';

    let message: { log?: string } = {};

    try {
        message = JSON.parse(event.message);
    } catch (e) {
        console.log('parse log error', e);
    }

    return format(new Date(event.timestamp), 'yyyy-MM-dd HH:mm') + ' ' + message?.log ?? '';
};

export const awsQueryResulToString = (queryResultItem: TAWSQueryResultItem): string => {
    if (!queryResultItem.length) return '';

    const fieldsMap = new Map();

    queryResultItem.forEach(({ field, value }) => fieldsMap.set(field, value));

    return fieldsMap.get('@timestamp').replace(/:\d+\.\d+/, '') + ' ' + fieldsMap.get('log');
};
