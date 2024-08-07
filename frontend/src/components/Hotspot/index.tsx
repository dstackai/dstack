import React from 'react';
import HotspotGeneral, { HotspotProps } from '@cloudscape-design/components/hotspot';

export interface IProps extends HotspotProps {
    renderHotspot?: boolean;
}

export const Hotspot: React.FC<IProps> = ({ renderHotspot = true, children, ...props }) => {
    if (!renderHotspot) {
        return children;
    }

    return <HotspotGeneral {...props}>{children}</HotspotGeneral>;
};
