declare interface IHub {
    id: number,
    hub_name: string,
    permission: 'read' | 'write'
    type: 'AWS',
    region?: string,
    bucket?: string,
}
