import { defineConfig } from 'tsdown'

/**
 * 自包含构建配置。
 *
 * 为什么强调「自包含」：从 git 安装的插件，pnpm 只会跑 `prepare` 脚本，
 * 拉下来的是源码而不是构建产物。所以 prepare 必须能在没有 monorepo
 * checkout、没有项目引用的前提下，直接把 src/ 转译出发布入口。
 *
 * 分发方式上我们刻意不走 git（git 安装需要用户给 allowBuilds 授权，
 * 等于允许该包在安装时于用户机器上执行代码，有供应链风险）。
 * 我们走 tarball：`pnpm pack` 出 .tgz，`dsh plugin add ./xxx.tgz` 安装，
 * 装的是预构建代码，用户无需任何构建授权。
 */
export default defineConfig({
  entry: ['src/index.ts'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'node22',
  // 类型的生成需要宿主的类型文件；而 @deepseek-ai/dsh-* 子包在 npm 上依赖图不完整
  // （实测：@deepseek-ai/dsh-type-meta 是 404），本地装不全。
  // 因此这里不产出 .d.ts —— 插件是被宿主加载的运行时包，类型由宿主侧保证。
  dts: false,
  clean: true,
  // 宿主提供的包一律不打包，交给 dsh 的模块解析（resolveBundleDir 从 dsh 安装目录优先解析）。
  // 注：tsdown 0.23 会提示 `external` 已废弃、建议改 `deps.neverBundle`；此处先沿用可用写法。
  external: [/^@deepseek-ai\//, /^node:/],
})
