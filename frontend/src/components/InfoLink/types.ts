import { LinkProps } from '@cloudscape-design/components/link';

export interface IProps {
    id?: string;
    ariaLabel?: string;
    onFollow: LinkProps['onFollow'];
}
