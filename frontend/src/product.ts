import { getProductConfig } from '../product.config.cjs';

export const product = getProductConfig(process.env.UI_VERSION);
