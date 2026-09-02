import type { PropertyFilterProps } from 'components';

export function filterLastElementByPrefix(
    arr: PropertyFilterProps.Query['tokens'],
    prefix: string,
): PropertyFilterProps.Query['tokens'] {
    // Ищем индекс последнего элемента с префиксом "test_"
    let lastTestIndex = -1;
    for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i].propertyKey?.startsWith(prefix)) {
            lastTestIndex = i;
            break;
        }
    }

    // Фильтруем массив
    return arr.filter((item, index) => {
        // Оставляем элемент, если:
        // 1. Это не строка с префиксом "test_"?
        // 2. ИЛИ это строка с префиксом "test_" И она последняя в массиве
        return !item.propertyKey?.startsWith(prefix) || index === lastTestIndex;
    });
}
