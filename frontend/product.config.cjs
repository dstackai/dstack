/* global module */
const oss = {
    id: 'oss',
    name: 'dstack',
    hasEvents: false,
    hasBilling: false,
    hasPresets: false,
    isSky: false,
};
const enterprise = { ...oss, id: 'enterprise', name: 'dstack Enterprise', hasEvents: true };
const factory = { ...enterprise, id: 'factory', name: 'dstack Factory', hasBilling: true, hasPresets: true };
const sky = { ...factory, id: 'sky', name: 'dstack Sky', isSky: true };

function getProductConfig(version) {
    switch (version) {
        case 'enterprise':
            return enterprise;
        case 'factory':
            return factory;
        case 'sky':
            return sky;
        default:
            return oss;
    }
}

module.exports = { getProductConfig };
