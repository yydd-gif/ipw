import { defineConfig } from 'tsdown'

/**
 * 自包含构建配置。
 *
 * 分发走 tarball：`pnpm pack` 出 .tgz，`dsh plugin add ./xxx.tgz` 安装。
 * 装的是预构建代码，用户无需 allowBuilds 授权。不要用 git 安装，也不要用
 * Windows 上会产出空目录的 `link:` 本地路径。
 *
 * 用 .mjs 而不是 .ts：tsdown 0.23 加载 TS 配置需要 `unrun`，而本包
 * `.npmrc` 关了 auto-install-peers / ignore-scripts，构建机不必再拉那一层。
 */
export default defineConfig({
  entry: ['src/index.ts', 'src/policy.ts'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'node22',
  // 类型的生成需要宿主的类型文件；而 @deepseek-ai/dsh-* 子包在 npm 上依赖图不完整
  // （实测：@deepseek-ai/dsh-type-meta 是 404），本地装不全。
  // 因此这里不产出 .d.ts —— 插件是被宿主加载的运行时包，类型由宿主侧保证。
  dts: false,
  clean: true,
  // 宿主提供的包一律不打包，交给 dsh 的模块解析。
  // tsdown 0.23+ 用 deps.neverBundle 替代已废弃的 external。
  deps: { neverBundle: [/^@deepseek-ai\//, /^node:/] },
})
