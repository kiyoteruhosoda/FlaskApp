// フロントエンドビルド完了時にコミットハッシュを表示する（`npm run build` の最終ステップ）。
// バックエンド側の scripts/generate_version.sh と同じ "vXXXXXXX" 表記に揃える。
import { execSync } from 'node:child_process';

function gitOutput(args) {
  try {
    return execSync(`git ${args}`, { cwd: new URL('..', import.meta.url), stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  } catch {
    return null;
  }
}

const commitHash = gitOutput('rev-parse --short HEAD') || 'unknown';
const branch = gitOutput('rev-parse --abbrev-ref HEAD') || 'unknown';
const version = commitHash === 'unknown' ? 'dev' : `v${commitHash}`;
const buildDate = new Date().toISOString();

console.log('======================================');
console.log(' Frontend build finished');
console.log(` Version : ${version}${branch !== 'main' && branch !== 'unknown' ? ` (${branch})` : ''}`);
console.log(` Commit  : ${commitHash}`);
console.log(` Built   : ${buildDate}`);
console.log('======================================');
