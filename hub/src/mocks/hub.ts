const listSuccess: IHub[] = new Array(50).fill({}).map((i, index) => ({
    id: index,
    hub_name: `hub_${index}`,
    permission: index < 8 ? 'write' : 'read',
    type: 'AWS',
    region: `hub_${index}_region`,
    bucket: `hub_${index}_bucket`,
}));

export default {
    list: {
        success: listSuccess,
    },
};
