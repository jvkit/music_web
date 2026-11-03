// 用法: node fp.mjs <8kHz单声道s16le裸PCM文件> [秒数，默认6] [起始偏移秒，默认4]
// 输出: base64 音频指纹（shazam_v2，官方客户端取「第4秒起的6秒」窗口）
import { readFileSync } from 'fs';
import { createRequire } from 'module';

// afp.js 是从浏览器抠出来的 Emscripten 胶水，Node 分支引用了裸 fs/path/require
globalThis.require = createRequire(import.meta.url);
globalThis.fs = require('fs');
globalThis.path = require('path');

const { InstantiateRuntime, GenerateFP } = await import('./afp.js');

const file = process.argv[2];
const seconds = parseInt(process.argv[3] || '6', 10);
const offsetSec = parseInt(process.argv[4] || '4', 10);
if (!file) {
    console.error('用法: node fp.mjs <pcm文件> [秒数] [偏移秒]');
    process.exit(1);
}

const pcm = readFileSync(file);
const start = offsetSec * 8000 * 2;
const need = start + seconds * 8000 * 2;
if (pcm.length < need) {
    console.error(`PCM 太短: 需要偏移${offsetSec}s+${seconds}s=${need} 字节，实际 ${pcm.length}`);
    process.exit(1);
}
const samples = new Float32Array(seconds * 8000);
for (let i = 0; i < samples.length; i++) {
    samples[i] = pcm.readInt16LE(start + i * 2) / 32768;
}

await InstantiateRuntime();
const fp = GenerateFP(samples);
process.stdout.write(fp);
