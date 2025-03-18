import { Mode } from '@cloudscape-design/global-styles';

export const getThemeMode = (): Mode => (window?.matchMedia('(prefers-color-scheme: dark)').matches ? Mode.Dark : Mode.Light);

export function getBaseUrl(): string {
    const { protocol, hostname, port } = window.location;
    return `${protocol}//${hostname}${port ? `:${port}` : ''}`;
}
