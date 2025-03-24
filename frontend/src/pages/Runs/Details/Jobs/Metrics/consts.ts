export const second = 1000;
export const minute = 60 * second;
export const hour = 60 * 60 * 1000;
export const startTime = Date.now().valueOf() - hour;

export const kByte = 1024;
export const MByte = kByte * 1024;
export const GByte = MByte * 1024;

export const ALL_CPU_USAGE = 'cpu_usage_percent';
export const ALL_MEMORY_USAGE = 'memory_usage_bytes';
export const EACH_CPU_USAGE_PREFIX = 'gpu_util_percent_gpu';
export const EACH_MEMORY_USAGE_PREFIX = 'gpu_memory_usage_bytes_gpu';
